import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from conftest import command

from skywatch_agent.agent import Agent
from skywatch_agent.contracts import timestamp


def test_replay_eof_observations_and_stop(config, transport, demo):
    _, scenarios = demo
    agent = Agent(config, transport, scenarios)
    agent.handle_command(command())
    assert transport.acks[-1]["accepted"]
    agent.replay_started -= 100
    for _ in range(100):
        agent.tick()
    assert agent.mode == "idle" and agent.source is None
    assert transport.observations
    assert all(item["captured_at"].startswith("2026-01-01") for item in transport.observations)
    assert all(item["scenario_id"] == "synthetic-motion" for item in transport.observations)
    agent.handle_command(command("stop", "stop"))
    assert transport.acks[-1]["accepted"]


def test_duplicate_command_does_not_restart_and_conflicting_id_rejected(config, transport, demo):
    _, scenarios = demo
    agent = Agent(config, transport, scenarios)
    original = command()
    try:
        agent.handle_command(original)
        source = agent.source
        agent.tick()
        index = source.index
        agent.handle_command(original)
        assert agent.source is source and source.index == index
        assert transport.acks[-1] == transport.acks[-2]
        agent.handle_command({**original, "command": "stop"})
        assert not transport.acks[-1]["accepted"] and agent.mode == "replay"
    finally:
        agent.stop()


def test_failed_replacement_preserves_running_source(config, transport, demo):
    _, scenarios = demo
    agent = Agent(config, transport, scenarios)
    try:
        agent.handle_command(command())
        source = agent.source
        agent.handle_command(command("bad", scenario_id="does-not-exist"))
        assert not transport.acks[-1]["accepted"]
        assert agent.source is source and agent.mode == "replay"
    finally:
        agent.stop()


def test_stop_is_responsive_while_waiting_for_replay_time(config, transport, demo):
    _, scenarios = demo
    agent = Agent(replace(config, replay_speed=0.01), transport, scenarios)
    agent.start("replay", "synthetic-motion")
    agent.tick()
    agent.tick()  # next frame is due ten seconds later
    transport.commands.put(command("stop", "stop"))
    start = time.monotonic()
    agent.tick()
    assert time.monotonic() - start < 0.5
    assert agent.mode == "idle" and transport.acks[-1]["accepted"]


def test_old_future_and_wrong_camera_commands(config, transport, demo):
    _, scenarios = demo
    agent = Agent(config, transport, scenarios)
    for i, delta in enumerate((-300, 300)):
        agent.handle_command(
            command(str(i), issued_at=timestamp(datetime.now(UTC) + timedelta(seconds=delta)))
        )
        assert not transport.acks[-1]["accepted"] and agent.source is None
    agent.handle_command(command("other", camera_id="camera_2"))
    assert len(transport.acks) == 2


def test_start_live_uses_same_pipeline_and_failed_capture_goes_idle(config, transport, demo):
    _, scenarios = demo
    from skywatch_agent.source import VideoSource

    def factory(**kwargs):
        return VideoSource(recording=scenarios["synthetic-motion"].recordings["camera_1"])

    agent = Agent(config, transport, scenarios, source_factory=factory)
    agent.handle_command(command(action="start_live"))
    assert agent.mode == "live" and agent.scenario_id is None
    for _ in range(60):
        agent.tick()
    assert transport.observations and all(x["mode"] == "live" for x in transport.observations)

    def broken():
        raise OSError("camera disconnected")

    agent.source.read = broken
    agent.tick()
    assert agent.mode == "idle"

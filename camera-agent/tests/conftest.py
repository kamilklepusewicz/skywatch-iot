import queue
from datetime import UTC, datetime

import pytest

from skywatch_agent.config import AgentConfig, DetectorConfig, MqttConfig, TrackerConfig
from skywatch_agent.contracts import timestamp, validate
from skywatch_agent.demo import generate_demo
from skywatch_agent.replay import load_scenarios


@pytest.fixture
def demo(tmp_path):
    directory = generate_demo(tmp_path / "demo")
    return directory, load_scenarios(tuple(directory.glob("*.json")))


@pytest.fixture
def config():
    return AgentConfig(
        "camera_1",
        MqttConfig(password="test-only"),
        DetectorConfig(kind="motion"),
        TrackerConfig(min_hits=1),
        replay_speed=1000,
        observation_interval=0.1,
    )


class MemoryTransport:
    def __init__(self):
        self.commands = queue.Queue()
        self.statuses, self.acks, self.observations = [], [], []

    def report_status(self, mode, scenario_id=None):
        self.statuses.append((mode, scenario_id))

    def ack(self, payload):
        validate("ack", payload)
        self.acks.append(payload)

    def observation(self, payload):
        validate("observation", payload)
        self.observations.append(payload)


@pytest.fixture
def transport():
    return MemoryTransport()


def command(command_id="command_1", action="start_replay", **overrides):
    return {
        "schema_version": 1,
        "camera_id": "camera_1",
        "command_id": command_id,
        "issued_at": timestamp(datetime.now(UTC)),
        "command": action,
        "scenario_id": "synthetic-motion",
        **overrides,
    }

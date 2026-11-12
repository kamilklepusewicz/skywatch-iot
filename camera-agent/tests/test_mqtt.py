import json
from types import SimpleNamespace

import pytest
from conftest import command

from skywatch_agent.mqtt_client import MqttClient


@pytest.mark.parametrize(
    "payload,retained,queued,acks",
    [
        (command(), False, 1, 0),
        (command(), True, 0, 1),
        (command(camera_id="camera_2"), False, 0, 0),
        ({**command(), "command": "delete_everything"}, False, 0, 1),
        ([], False, 0, 0),
    ],
)
def test_command_validation_and_retained_rejection(config, payload, retained, queued, acks):
    transport = MqttClient(config.camera_id, config.mqtt)
    rejected = []
    transport.reject = lambda *args: rejected.append(args)
    message = SimpleNamespace(
        topic="skywatch/cameras/camera_1/commands",
        payload=json.dumps(payload).encode(),
        retain=retained,
    )
    transport._on_message(None, None, message)
    assert transport.commands.qsize() == queued
    assert len(rejected) == acks


def test_corrupt_and_oversized_payloads_do_not_crash_network_thread(config):
    transport = MqttClient(config.camera_id, config.mqtt)
    for raw in (b"{", b"\xff", b"x" * 17000, b"[" * 2000 + b"]" * 2000):
        transport._on_message(
            None,
            None,
            SimpleNamespace(topic="skywatch/cameras/camera_1/commands", payload=raw, retain=False),
        )
    assert transport.commands.empty()


def test_publish_qos_retain_and_bounded_queue(config):
    transport = MqttClient(config.camera_id, config.mqtt)
    calls = []

    def publish(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(rc=0)

    transport.client.publish = publish
    transport.report_status("replay", "scenario")
    transport.reject("command", "test")
    assert [call[1]["qos"] for call in calls] == [1, 1]
    assert [call[1]["retain"] for call in calls] == [True, False]
    assert json.loads(transport.client._will_payload)["online"] is False
    assert transport.client._will_qos == 1 and transport.client._will_retain
    transport.client.publish = lambda *args, **kwargs: SimpleNamespace(rc=15)
    with pytest.raises(BufferError):
        transport.publish("status", "camera-status", transport.current_status, retain=True)

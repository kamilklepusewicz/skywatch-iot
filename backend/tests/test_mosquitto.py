import json
import os
import shutil
import socket
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from queue import Queue
from threading import Event

import paho.mqtt.client as mqtt
import pytest
from fastapi.testclient import TestClient
from test_service import sample

from app.config import Settings
from app.main import create_app

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic-replay.json"


def eventually(lookup, predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        result = lookup()
        if predicate(result):
            return result
        time.sleep(0.05)
    pytest.fail("Broker or application did not reach the expected state")


@pytest.fixture
def local_broker(tmp_path):
    executable = os.environ.get("MOSQUITTO_BIN") or shutil.which("mosquitto")
    if not executable:
        pytest.skip("Set MOSQUITTO_BIN or add Mosquitto to PATH for this integration test")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    conf = tmp_path / "mosquitto.conf"
    conf.write_text(f"listener {port} 127.0.0.1\nallow_anonymous true\n", encoding="utf-8")
    with subprocess.Popen(
        [executable, "-c", str(conf)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    ) as process:
        try:
            yield port
        finally:
            process.terminate()
            process.wait(timeout=5)


def test_v1_over_mosquitto(tmp_path, local_broker):
    from app.database import Store
    from app.replay import import_file

    port = local_broker
    settings = Settings(
        database_path=tmp_path / "test.sqlite3",
        mqtt_username="",
        mqtt_port=port,
        adsb_enabled=False,
        command_timeout_seconds=2,
    )
    store = Store(settings.db_path)
    try:
        import_file(store, FIXTURE)
    finally:
        store.close()

    subscribed = Event()
    commands = Queue()
    agent = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311)
    agent.on_connect = lambda client, *args: client.subscribe("skywatch/cameras/+/commands", qos=1)
    agent.on_subscribe = lambda *args: subscribed.set()
    agent.on_message = lambda client, userdata, msg: commands.put_nowait(msg)
    agent.connect_async("127.0.0.1", port)
    agent.loop_start()

    def publish(camera, topic, body, *, retain=False):
        info = agent.publish(
            f"skywatch/cameras/{camera}/{topic}", json.dumps(body), qos=1, retain=retain
        )
        info.wait_for_publish(2)
        assert info.is_published()

    try:
        assert subscribed.wait(5)
        with TestClient(create_app(settings)) as client:

            def get(path):
                response = client.get(f"/api/{path}")
                assert response.is_success, response.text
                return response.json()

            eventually(lambda: get("health"), lambda item: item["mqtt_subscribed"])
            with client.websocket_connect("/ws") as ws:
                assert ws.receive_json()["type"] == "ready"
                for camera in ("camera_1", "camera_2"):
                    status = sample(
                        "camera-status",
                        camera_id=camera,
                        online=True,
                        mode="live",
                        reported_at=datetime.now(UTC).isoformat(),
                    )
                    publish(camera, "status", status, retain=True)
                    observation = sample(
                        "observation",
                        camera_id=camera,
                        observation_id=camera,
                        mode="replay",
                        scenario_id="synthetic_pair",
                        captured_at="2026-01-02T12:00:00Z",
                        object_type="airplane",
                    )
                    publish(camera, "observations", observation)
                    publish(camera, "observations", observation)
                assert ws.receive_json()["type"] == "changed"
                eventually(lambda: get("cameras"), lambda items: all(x["online"] for x in items))
                history = eventually(lambda: get("observations"), lambda items: len(items) == 2)
                assert all(x["match"]["synthetic"] for x in history)
                for index in (1, 2):
                    detail = get(f"observations/camera_{index}")
                    (found,) = detail["match"]["candidates"]
                    assert found["aircraft"]["callsign"] == f"SYNTH0{index}"
                assert get("aircraft")["snapshot"] is None
                assert get("aircraft?mode=replay&scenario_id=synthetic_pair")["synthetic"]

                response = client.post(
                    "/api/cameras/camera_1/commands",
                    json={"command": "start_replay", "scenario_id": "synthetic_pair"},
                )
                assert response.status_code == 202
                command_id = response.json()["command_id"]
                message = commands.get(timeout=3)
                assert message.topic == "skywatch/cameras/camera_1/commands"
                assert message.qos == 1 and not message.retain
                assert json.loads(message.payload)["scenario_id"] == "synthetic_pair"
                ack = sample(
                    "ack",
                    camera_id="camera_1",
                    command_id=command_id,
                    accepted=True,
                    reported_at=datetime.now(UTC).isoformat(),
                )
                publish("camera_1", "ack", ack)
                eventually(
                    lambda: get(f"commands/{command_id}"), lambda x: x["status"] == "accepted"
                )
    finally:
        agent.disconnect()
        agent.loop_stop()


def test_queued_qos_one_command_delivers_on_connect(tmp_path, local_broker):
    from app.database import Store
    from app.models import CommandRequest
    from app.mqtt import Broker
    from app.service import Service

    settings = Settings(
        database_path=tmp_path / "queued.sqlite3", mqtt_username="", mqtt_port=local_broker
    )
    store = Store(settings.db_path)
    broker = Broker(settings)
    service = Service(settings, store, broker)
    messages = Queue()
    subscribed = Event()
    receiver = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    topic = "skywatch/cameras/camera_1/commands"
    receiver.on_connect = lambda client, *args: client.subscribe(topic, qos=1)
    receiver.on_subscribe = lambda *args: subscribed.set()
    receiver.on_message = lambda client, userdata, msg: messages.put_nowait(msg)
    receiver.connect_async("127.0.0.1", local_broker)
    receiver.loop_start()
    try:
        assert subscribed.wait(5)
        # Simulate the callback race: the subscription flag is set, but Paho has no socket.
        broker.subscribed.set()
        result = service.issue("camera_1", CommandRequest(command="stop"), datetime.now(UTC))
        assert result.status == "delivery_uncertain"
        broker.subscribed.clear()
        broker.start()
        message = messages.get(timeout=5)
        assert message.qos == 1 and not message.retain
        assert json.loads(message.payload)["command_id"] == result.command_id
        assert broker.subscribed.wait(5)
        ack = sample(
            "ack",
            camera_id="camera_1",
            command_id=result.command_id,
            accepted=True,
            reported_at=datetime.now(UTC).isoformat(),
        )
        receiver.publish("skywatch/cameras/camera_1/ack", json.dumps(ack), qos=1)
        service.ingest(broker.messages.get(timeout=5))
        assert store.command(result.command_id).status == "accepted"
    finally:
        broker.stop()
        receiver.disconnect()
        receiver.loop_stop()
        store.close()

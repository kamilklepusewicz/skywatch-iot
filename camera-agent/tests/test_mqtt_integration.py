"""Real authenticated Mosquitto, separate agent processes, reconnect and Last Will."""

import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

import paho.mqtt.client as mqtt
import pytest
from conftest import command

from skywatch_agent.config import MqttConfig
from skywatch_agent.contracts import validate
from skywatch_agent.mqtt_client import MqttClient

pytestmark = pytest.mark.integration


def eventually(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Timed out waiting for condition")


class Broker:
    def __init__(self, directory, executable, passwd_executable):
        self.executable = executable
        self.password = secrets.token_hex(16)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            self.port = sock.getsockname()[1]
        passwords = directory / "passwords"
        subprocess.run(
            [passwd_executable, "-b", "-c", str(passwords), "skywatch", self.password],
            check=True,
            capture_output=True,
        )
        self.config = directory / "mosquitto.conf"
        self.config.write_text(
            f"listener {self.port} 127.0.0.1\nallow_anonymous false\n"
            f"password_file {passwords}\npersistence false\n"
        )
        self.log = (directory / "broker.log").open("w+")
        self.process = None

    def start(self):
        self.process = subprocess.Popen(
            [self.executable, "-c", str(self.config)], stdout=self.log, stderr=self.log
        )

        def listening():
            if self.process.poll() is not None:
                self.log.seek(0)
                raise AssertionError(self.log.read())
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.1):
                    return True
            except OSError:
                return False

        eventually(listening)

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=5)


@pytest.fixture
def broker(tmp_path):
    executable = os.environ.get("MOSQUITTO_BIN") or shutil.which("mosquitto")
    passwd = os.environ.get("MOSQUITTO_PASSWD_BIN") or shutil.which("mosquitto_passwd")
    if not executable or not passwd:
        pytest.skip("Install mosquitto and mosquitto_passwd to run real MQTT integration tests")
    broker = Broker(tmp_path, executable, passwd)
    broker.start()
    try:
        yield broker
    finally:
        broker.stop()
        broker.log.close()


class Observer:
    def __init__(self, broker):
        self.condition = threading.Condition()
        self.messages = []
        self.ready = threading.Event()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.username_pw_set("skywatch", broker.password)
        self.client.on_connect = lambda client, *_: client.subscribe("skywatch/#", qos=1)
        self.client.on_subscribe = lambda *_: self.ready.set()
        self.client.on_disconnect = lambda *_: self.ready.clear()
        self.client.on_message = self.received
        self.client.connect("127.0.0.1", broker.port)
        self.client.loop_start()
        assert self.ready.wait(5)

    def received(self, client, userdata, message):
        with self.condition:
            self.messages.append(
                (message.topic, json.loads(message.payload), message.qos, message.retain)
            )
            self.condition.notify_all()

    def wait(self, suffix, camera_id, predicate=lambda _: True, timeout=10):
        deadline = time.monotonic() + timeout
        with self.condition:
            while True:
                for i, message in enumerate(self.messages):
                    topic, data, _, _ = message
                    if topic == f"skywatch/cameras/{camera_id}/{suffix}" and predicate(data):
                        return self.messages.pop(i)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AssertionError(f"No matching {camera_id}/{suffix}: {self.messages}")
                self.condition.wait(remaining)

    def send(self, payload, retain=False):
        self.client.publish(
            f"skywatch/cameras/{payload['camera_id']}/commands",
            json.dumps(payload),
            qos=1,
            retain=retain,
        ).wait_for_publish(5)

    def close(self):
        self.client.disconnect()
        self.client.loop_stop()


def test_two_processes_replay_qos_ack_stop_retained_and_last_will(broker, demo, tmp_path):
    directory, _ = demo
    observer = Observer(broker)
    processes, logs = [], []
    environment = {
        **os.environ,
        "MQTT_HOST": "127.0.0.1",
        "MQTT_PORT": str(broker.port),
        "MQTT_USERNAME": "skywatch",
        "MQTT_PASSWORD": broker.password,
    }
    try:
        observer.send(command("retained", "start_replay"), retain=True)
        for camera_id in ("camera_1", "camera_2"):
            log = (tmp_path / f"{camera_id}.log").open("w+")
            logs.append(log)
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "skywatch_agent",
                    "run",
                    "--config",
                    str(directory / f"{camera_id}.toml"),
                ],
                env=environment,
                stdout=log,
                stderr=log,
            )
            processes.append(process)
            observer.wait("status", camera_id, lambda p: p["online"] and p["mode"] == "idle")
        rejected = observer.wait("ack", "camera_1", lambda p: p["command_id"] == "retained")[1]
        assert not rejected["accepted"]
        starts = [command(f"start-{i}", camera_id=f"camera_{i}") for i in (1, 2)]
        for payload in starts:
            observer.send(payload)
            ack = observer.wait(
                "ack", payload["camera_id"], lambda p: p["command_id"] == payload["command_id"]
            )
            assert ack[1]["accepted"] and ack[2] == 1 and not ack[3]
        first_ack = ack[1]
        for camera_id in ("camera_1", "camera_2"):
            _, observation, qos, retained = observer.wait("observations", camera_id)
            validate("observation", observation)
            assert observation["captured_at"].startswith("2026-01-01")
            assert observation["scenario_id"] == "synthetic-motion"
            assert qos == 1 and not retained
        observer.send(starts[1])
        assert (
            observer.wait("ack", "camera_2", lambda p: p["command_id"] == "start-2")[1] == first_ack
        )
        observer.send(command("stop", "stop"))
        assert observer.wait("ack", "camera_1", lambda p: p["command_id"] == "stop")[1]["accepted"]
        observer.wait("status", "camera_1", lambda p: p["mode"] == "idle")
        processes[1].kill()
        processes[1].wait(timeout=5)
        observer.wait("status", "camera_2", lambda p: not p["online"])
        later = Observer(broker)
        try:
            retained_offline = later.wait("status", "camera_2", lambda p: not p["online"])
            assert retained_offline[3]
        finally:
            later.close()
        assert processes[0].poll() is None
        observer.send(command("still-alive", "start_replay"))
        assert observer.wait("ack", "camera_1", lambda p: p["command_id"] == "still-alive")[1][
            "accepted"
        ]
        processes[0].terminate()
        assert processes[0].wait(timeout=5) == 0
        observer.wait("status", "camera_1", lambda p: not p["online"])
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
        observer.close()
        for log in logs:
            log.close()


def test_reconnect_resubscribes_and_republishes_current_status(broker):
    config = MqttConfig(port=broker.port, password=broker.password)
    transport = MqttClient("camera_1", config)
    observer = Observer(broker)
    acknowledged = []
    transport.client.on_publish = lambda client, userdata, mid, reason, properties: (
        acknowledged.append(mid)
    )
    try:
        transport.start()
        transport.report_status("replay", "historical")
        observer.wait("status", "camera_1", lambda p: p["mode"] == "replay")
        broker.stop()
        eventually(lambda: not transport.ready.is_set())
        payload = json.loads(
            (Path(__file__).parents[2] / "shared/examples/observation.json").read_text()
        )
        pending = transport.observation(payload)
        broker.start()
        assert transport.ready.wait(10) and observer.ready.wait(10)
        # Paho retains MQTT_ERR_NO_CONN in MessageInfo even after a queued QoS 1
        # publish is delivered. The broker's PUBACK/on_publish is the proof of delivery.
        eventually(lambda: pending.mid in acknowledged)
        transport.report_status("replay", "historical")
        status = observer.wait("status", "camera_1", lambda p: p["mode"] == "replay")[1]
        assert status["scenario_id"] == "historical" and status["online"]
        observer.send(command("after-reconnect", "stop"))
        assert transport.commands.get(timeout=5)["command_id"] == "after-reconnect"
    finally:
        transport.close()
        observer.close()


def test_wrong_password_is_rejected(broker):
    config = MqttConfig(port=broker.port, password=broker.password, connect_timeout=0.5)
    transport = MqttClient("unauthorized", replace(config, password="incorrect"))
    with pytest.raises(ConnectionError):
        transport.start()

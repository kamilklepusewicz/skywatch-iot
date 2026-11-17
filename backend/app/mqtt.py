import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from queue import Full, Queue
from threading import Event

import paho.mqtt.client as paho
from jsonschema import Draft202012Validator

from .config import Settings
from .models import Command, PublishStatus

LOG = logging.getLogger(__name__)
TOPIC_ROOT = "skywatch/cameras"
CONTRACTS = Path(__file__).resolve().parents[2] / "shared" / "contracts"
SUFFIXES = {"observations": "observation", "status": "camera-status", "ack": "ack"}


@dataclass(frozen=True, slots=True)
class Message:
    topic: str
    payload: bytes
    retained: bool
    received_at: datetime


def contracts() -> dict[str, Draft202012Validator]:
    return {
        name: Draft202012Validator(
            json.loads((CONTRACTS / f"{name}.schema.json").read_text(encoding="utf-8")),
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        )
        for name in (*SUFFIXES.values(), "command")
    }


class Broker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.messages: Queue[Message] = Queue(maxsize=2048)
        self.connected = Event()
        self.subscribed = Event()
        self.client = paho.Client(paho.CallbackAPIVersion.VERSION2, protocol=paho.MQTTv311)
        password = settings.mqtt_password
        if settings.mqtt_username:
            self.client.username_pw_set(
                settings.mqtt_username,
                password.get_secret_value() if password else None,
            )
        self.client.max_queued_messages_set(32)
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.on_connect = self._connect
        self.client.on_connect_fail = self._connect_fail
        self.client.on_disconnect = self._disconnect
        self.client.on_subscribe = self._subscribe
        self.client.on_message = self._receive

    def start(self) -> None:
        self.client.connect_async(self.settings.mqtt_host, self.settings.mqtt_port, keepalive=30)
        self.client.loop_start()

    def stop(self) -> None:
        self.client.disconnect()
        self.client.loop_stop()
        self.connected.clear()
        self.subscribed.clear()

    def publish(self, command: Command) -> PublishStatus:
        if not self.subscribed.is_set():
            return "publish_failed"
        info = self.client.publish(
            f"{TOPIC_ROOT}/{command.camera_id}/commands",
            command.model_dump_json(),
            qos=1,
            retain=False,
        )
        if info.rc == paho.MQTT_ERR_SUCCESS:
            return "pending"
        if info.rc == paho.MQTT_ERR_QUEUE_SIZE:
            LOG.warning("mqtt_command_queue_full command_id=%s", command.command_id)
            return "publish_failed"
        # NO_CONN can leave a QoS 1 packet in Paho's queue for the next connection.
        LOG.warning(
            "mqtt_command_delivery_uncertain command_id=%s rc=%s", command.command_id, info.rc
        )
        return "delivery_uncertain"

    def _connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            LOG.warning("mqtt_connection_rejected reason=%s", reason_code)
            return
        self.connected.set()
        subscriptions = [(f"{TOPIC_ROOT}/+/{suffix}", 1) for suffix in SUFFIXES]
        rc, _ = client.subscribe(subscriptions)
        if rc != paho.MQTT_ERR_SUCCESS:
            LOG.error("mqtt_subscription_failed rc=%s", rc)

    def _connect_fail(self, client, userdata) -> None:
        LOG.warning(
            "mqtt_broker_unreachable host=%s port=%s",
            self.settings.mqtt_host,
            self.settings.mqtt_port,
        )

    def _subscribe(self, client, userdata, mid, reason_codes, properties) -> None:
        if len(reason_codes) != len(SUFFIXES) or any(code.is_failure for code in reason_codes):
            LOG.error("mqtt_subscription_rejected reasons=%s", reason_codes)
            return
        self.subscribed.set()
        LOG.info("mqtt_subscribed topics=%s", ",".join(SUFFIXES))

    def _disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        self.subscribed.clear()
        self.connected.clear()
        LOG.info("mqtt_disconnected reason=%s", reason_code)

    def _receive(self, client, userdata, message) -> None:
        if len(message.payload) > 16_384:
            LOG.warning("mqtt_payload_too_large topic=%s", message.topic)
            return
        try:
            self.messages.put_nowait(
                Message(
                    message.topic,
                    message.payload,
                    message.retain,
                    datetime.now(UTC),
                )
            )
        except Full:
            LOG.warning("mqtt_ingress_full topic=%s", message.topic)

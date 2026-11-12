import json
import logging
import queue
import threading

import paho.mqtt.client as mqtt
from jsonschema import ValidationError

from .config import MqttConfig
from .contracts import status, timestamp, validate

LOG = logging.getLogger(__name__)


class MqttClient:
    def __init__(self, camera_id: str, config: MqttConfig):
        if not config.password:
            raise ValueError("Set MQTT_PASSWORD in the environment before connecting")
        self.camera_id = camera_id
        self.config = config
        self.prefix = f"skywatch/cameras/{camera_id}"
        self.commands: queue.Queue[dict] = queue.Queue(maxsize=100)
        self.ready = threading.Event()
        self.lock = threading.Lock()
        self.current_status = status(camera_id, True, "idle")
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"skywatch-{camera_id}",
            clean_session=True,
            protocol=mqtt.MQTTv311,
        )
        self.client.username_pw_set(config.username, config.password)
        self.client.max_queued_messages_set(config.queue_size)
        self.client.max_inflight_messages_set(20)
        self.client.reconnect_delay_set(min_delay=1, max_delay=15)
        self.client.will_set(
            f"{self.prefix}/status",
            json.dumps(status(camera_id, False, "idle")),
            qos=1,
            retain=True,
        )
        self.client.on_connect = self._on_connect
        self.client.on_subscribe = self._on_subscribe
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            LOG.error("Broker rejected MQTT connection: %s", reason_code)
            return
        client.subscribe(f"{self.prefix}/commands", qos=1)
        with self.lock:
            current = dict(self.current_status)
        current["reported_at"] = timestamp()
        self._safe_publish("status", "camera-status", current, retain=True)

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties):
        if any(code.is_failure for code in reason_codes):
            LOG.error("Broker rejected command subscription")
        else:
            self.ready.set()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.ready.clear()
        if reason_code.is_failure:
            LOG.warning("MQTT disconnected; reconnecting automatically")

    def _on_message(self, client, userdata, message):
        if message.topic != f"{self.prefix}/commands":
            return
        if len(message.payload) > 16_384:
            LOG.warning("Ignoring oversized command")
            return
        payload = None
        try:
            payload = json.loads(message.payload)
            validate("command", payload)
            if payload["camera_id"] != self.camera_id:
                LOG.warning("Ignoring command addressed to another camera")
                return
            if message.retain:
                self.reject(payload["command_id"], "Retained commands are not executed")
                return
            self.commands.put_nowait(payload)
        except (ValueError, UnicodeError, RecursionError, ValidationError, queue.Full) as exc:
            LOG.warning("Invalid command or full command queue: %s", type(exc).__name__)
            if (
                isinstance(payload, dict)
                and payload.get("camera_id") == self.camera_id
                and isinstance(payload.get("command_id"), str)
                and payload["command_id"]
            ):
                self.reject(payload["command_id"], "Invalid command or command queue is full")

    def reject(self, command_id: str, message: str):
        self._safe_publish(
            "ack",
            "ack",
            {
                "schema_version": 1,
                "camera_id": self.camera_id,
                "command_id": command_id,
                "reported_at": timestamp(),
                "accepted": False,
                "message": message,
            },
        )

    def start(self):
        self.client.connect_async(self.config.host, self.config.port, self.config.keepalive)
        self.client.loop_start()
        if not self.ready.wait(self.config.connect_timeout):
            self.client.disconnect()
            self.client.loop_stop()
            raise ConnectionError("MQTT connect/subscribe timed out; check broker and credentials")

    def publish(self, suffix: str, kind: str, payload: dict, retain: bool = False):
        validate(kind, payload)
        info = self.client.publish(
            f"{self.prefix}/{suffix}",
            json.dumps(payload, allow_nan=False),
            qos=1,
            retain=retain,
        )
        # Paho queues QoS 1 messages during a temporary disconnection.
        if info.rc not in (mqtt.MQTT_ERR_SUCCESS, mqtt.MQTT_ERR_NO_CONN):
            raise BufferError(f"MQTT publish queue rejected {suffix}: {info.rc}")
        return info

    def _safe_publish(self, suffix, kind, payload, retain=False):
        try:
            return self.publish(suffix, kind, payload, retain)
        except BufferError:
            LOG.error("MQTT queue full; dropped %s message", suffix)
            return None

    def report_status(self, mode: str, scenario_id: str | None = None):
        current = status(self.camera_id, True, mode, scenario_id)
        with self.lock:
            self.current_status = current
        self._safe_publish("status", "camera-status", current, retain=True)

    def observation(self, payload: dict):
        return self.publish("observations", "observation", payload)

    def ack(self, payload: dict):
        self._safe_publish("ack", "ack", payload)

    def close(self):
        with self.lock:
            self.current_status = status(self.camera_id, False, "idle")
            current = dict(self.current_status)
        try:
            info = self.publish("status", "camera-status", current, retain=True)
            if info is not None:
                info.wait_for_publish(timeout=3)
                if not info.is_published():
                    LOG.warning("Offline status was not confirmed before shutdown")
        except (BufferError, RuntimeError):
            LOG.warning("Unable to confirm offline status during shutdown")
        finally:
            self.client.disconnect()
            self.client.loop_stop()

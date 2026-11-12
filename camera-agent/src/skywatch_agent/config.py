import math
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


def positive(value: float, name: str) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and greater than zero")


@dataclass(frozen=True)
class MqttConfig:
    host: str = "127.0.0.1"
    port: int = 1883
    username: str = "skywatch"
    password: str = field(default="", repr=False)
    keepalive: int = 15
    connect_timeout: float = 10
    queue_size: int = 1000

    def __post_init__(self):
        if not self.host or not self.username:
            raise ValueError("MQTT_HOST and MQTT_USERNAME must be configured")
        if not 1 <= self.port <= 65535:
            raise ValueError("MQTT port must be between 1 and 65535")
        for name in ("keepalive", "connect_timeout", "queue_size"):
            positive(getattr(self, name), name)


@dataclass(frozen=True)
class DetectorConfig:
    kind: str = "yolo"
    model: Path | None = None
    confidence: float = 0.35
    nms_iou: float = 0.45
    image_size: int = 640
    min_area: float = 0.00005
    max_area: float = 0.10
    warmup_frames: int = 20

    def __post_init__(self):
        if self.kind not in ("yolo", "motion"):
            raise ValueError("detector.kind must be yolo or motion")
        if not 0 < self.confidence <= 1 or not 0 < self.nms_iou <= 1:
            raise ValueError("confidence and nms_iou must be in (0, 1]")
        if self.image_size < 32 or self.image_size % 32:
            raise ValueError("image_size must be a positive multiple of 32")
        if not 0 < self.min_area < self.max_area <= 1 or self.warmup_frames < 1:
            raise ValueError("Invalid motion detector area or warmup_frames")


@dataclass(frozen=True)
class TrackerConfig:
    max_distance: float = 0.08
    max_missed: int = 8
    min_hits: int = 3

    def __post_init__(self):
        positive(self.max_distance, "tracker.max_distance")
        if self.max_missed < 0 or self.min_hits < 1:
            raise ValueError("max_missed >= 0 and min_hits >= 1 required")


@dataclass(frozen=True)
class AgentConfig:
    camera_id: str
    mqtt: MqttConfig
    detector: DetectorConfig
    tracker: TrackerConfig
    scenario_files: tuple[Path, ...] = ()
    live_device: int | str = 0
    heartbeat_seconds: float = 10
    observation_interval: float = 0.5
    replay_speed: float = 1
    command_max_age: float = 120

    def __post_init__(self):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", self.camera_id):
            raise ValueError("camera_id may contain only letters, digits, underscore and hyphen")
        if isinstance(self.live_device, str) and not self.live_device.startswith("/dev/video"):
            raise ValueError("live_device must be a camera index or /dev/video device")
        for name in (
            "heartbeat_seconds",
            "observation_interval",
            "replay_speed",
            "command_max_age",
        ):
            positive(getattr(self, name), name)


def load_config(path: Path) -> AgentConfig:
    path = path.resolve()
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    mqtt = data.pop("mqtt", {})
    for key in ("host", "port", "username", "password"):
        if f"MQTT_{key.upper()}" in os.environ:
            mqtt[key] = os.environ[f"MQTT_{key.upper()}"]
    if "port" in mqtt:
        mqtt["port"] = int(mqtt["port"])
    detector = data.pop("detector", {})
    if detector.get("model"):
        detector["model"] = (path.parent / detector["model"]).resolve()
    tracker = data.pop("tracker", {})
    scenarios = tuple((path.parent / p).resolve() for p in data.pop("scenario_files", []))
    return AgentConfig(
        mqtt=MqttConfig(**mqtt),
        detector=DetectorConfig(**detector),
        tracker=TrackerConfig(**tracker),
        scenario_files=scenarios,
        **data,
    )

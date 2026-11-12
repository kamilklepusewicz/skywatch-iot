import json
from dataclasses import replace
from importlib.resources import files
from pathlib import Path

import pytest
from jsonschema import ValidationError

from skywatch_agent.config import DetectorConfig, load_config
from skywatch_agent.contracts import parse_time, validate

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name", ["observation", "command", "ack", "camera-status"])
def test_packaged_contract_matches_shared_and_accepts_example(name):
    shared = REPO / "shared" / "contracts" / f"{name}.schema.json"
    assert (
        files("skywatch_agent").joinpath(f"schemas/{name}.schema.json").read_bytes()
        == shared.read_bytes()
    )
    validate(name, json.loads((REPO / "shared" / "examples" / f"{name}.json").read_text()))


@pytest.mark.parametrize(
    "field,value",
    [("issued_at", "not-a-date"), ("schema_version", 2), ("camera_id", "../bad"), ("extra", True)],
)
def test_invalid_commands_fail_schema(field, value):
    payload = json.loads((REPO / "shared/examples/command.json").read_text())
    payload[field] = value
    with pytest.raises(ValidationError):
        validate("command", payload)


def test_config_resolves_paths_and_environment(monkeypatch, tmp_path):
    path = tmp_path / "camera.toml"
    path.write_text(
        'camera_id="camera_2"\nscenario_files=["s.json"]\n[detector]\nmodel="weights.onnx"\n'
    )
    monkeypatch.setenv("MQTT_PASSWORD", "not-printed")
    monkeypatch.setenv("MQTT_HOST", "192.168.1.10")
    monkeypatch.setenv("MQTT_PORT", "1884")
    config = load_config(path)
    assert config.mqtt.host == "192.168.1.10" and config.mqtt.port == 1884
    assert config.detector.model == tmp_path / "weights.onnx"
    assert config.scenario_files == (tmp_path / "s.json",)
    assert "not-printed" not in repr(config)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"camera_id": "bad/+"},
        {"replay_speed": 0},
        {"observation_interval": float("nan")},
        {"live_device": "https://example.com/video"},
    ],
)
def test_config_rejects_invalid_values(config, kwargs):
    with pytest.raises(ValueError):
        replace(config, **kwargs)


def test_detector_configuration_and_naive_time_are_rejected():
    with pytest.raises(ValueError):
        DetectorConfig(kind="fake")
    with pytest.raises(ValueError):
        parse_time("2026-01-01T12:00:00")

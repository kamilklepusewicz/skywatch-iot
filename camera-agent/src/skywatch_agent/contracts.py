"""Validate every wire message against the unchanged, packaged v1 schemas."""

import json
from datetime import UTC, datetime
from importlib.resources import files

from jsonschema import Draft202012Validator, FormatChecker

VALIDATORS = {
    name: Draft202012Validator(
        json.loads(files("skywatch_agent").joinpath(f"schemas/{name}.schema.json").read_text()),
        format_checker=FormatChecker(),
    )
    for name in ("observation", "command", "ack", "camera-status")
}


def validate(kind: str, payload: dict) -> dict:
    VALIDATORS[kind].validate(payload)
    return payload


def timestamp(value: datetime | None = None) -> str:
    return (value or datetime.now(UTC)).astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp must include a UTC offset or Z")
    return result.astimezone(UTC)


def status(camera_id: str, online: bool, mode: str, scenario_id: str | None = None) -> dict:
    return validate(
        "camera-status",
        {
            "schema_version": 1,
            "camera_id": camera_id,
            "reported_at": timestamp(),
            "online": online,
            "mode": mode,
            "scenario_id": scenario_id,
        },
    )

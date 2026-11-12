import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .contracts import parse_time


@dataclass(frozen=True)
class Recording:
    path: Path
    captured_start: datetime
    # Optional original presentation timestamps, seconds from the first frame.
    frame_offsets: tuple[float, ...] | None = None


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    recordings: dict[str, Recording]
    synthetic: bool


def load_scenarios(paths: tuple[Path, ...]) -> dict[str, Scenario]:
    result = {}
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        scenario_id = data["scenario_id"]
        if not isinstance(scenario_id, str) or not scenario_id.strip() or scenario_id in result:
            raise ValueError(f"Empty or duplicated scenario_id in {path}")
        recordings = {}
        for camera_id, item in data["cameras"].items():
            offsets = None
            if item.get("frame_offsets"):
                offsets = tuple(json.loads((path.parent / item["frame_offsets"]).read_text()))
                if (
                    not offsets
                    or offsets[0] != 0
                    or any(not math.isfinite(x) or x < 0 for x in offsets)
                    or any(a >= b for a, b in zip(offsets, offsets[1:]))
                ):
                    raise ValueError(f"Invalid frame offsets for {camera_id}")
            recordings[camera_id] = Recording(
                (path.parent / item["video"]).resolve(),
                parse_time(item["captured_start"]),
                offsets,
            )
        if not recordings:
            raise ValueError(f"No cameras in scenario {scenario_id}")
        result[scenario_id] = Scenario(scenario_id, recordings, bool(data.get("synthetic", False)))
    return result

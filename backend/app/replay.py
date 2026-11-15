import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from .adsb import normalize
from .config import Settings
from .database import Store
from .models import CameraId, ReplayId, Scenario


class RecordedSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retrieved_at: AwareDatetime | None = None
    response: dict[str, Any]


class ScenarioImport(Scenario):
    model_config = ConfigDict(extra="forbid")

    snapshots: list[RecordedSnapshot] = Field(default_factory=list)
    camera_starts: dict[CameraId, AwareDatetime] = Field(default_factory=dict)


class AgentRecording(BaseModel):
    captured_start: AwareDatetime


class AgentManifest(BaseModel):
    scenario_id: ReplayId
    synthetic: bool = False
    cameras: dict[CameraId, AgentRecording] = Field(min_length=1)


def validate_recordings(manifest: ScenarioImport, path: Path) -> None:
    agent = AgentManifest.model_validate_json(path.read_text(encoding="utf-8-sig"), strict=True)
    if agent.scenario_id != manifest.scenario_id:
        raise ValueError("Agent and backend scenario IDs differ")
    if agent.synthetic and not manifest.synthetic:
        raise ValueError("The backend must label synthetic agent recordings as synthetic")
    if manifest.cameras and manifest.cameras.keys() != agent.cameras.keys():
        raise ValueError("Agent and backend camera IDs differ")
    if manifest.camera_starts:
        starts = {key: spec.captured_start for key, spec in agent.cameras.items()}
        if starts != manifest.camera_starts:
            raise ValueError("Agent and backend capture times differ")


def import_file(store: Store, path: Path, *, agent_manifest: Path | None = None) -> Scenario:
    manifest = ScenarioImport.model_validate(json.loads(path.read_text(encoding="utf-8-sig")))
    if manifest.camera_starts and manifest.camera_starts.keys() != manifest.cameras.keys():
        raise ValueError("camera_starts must describe the registered cameras")
    if agent_manifest is not None:
        validate_recordings(manifest, agent_manifest)
    scenario = Scenario.model_validate(manifest.model_dump(exclude={"snapshots", "camera_starts"}))
    snapshots = [
        normalize(item.response, item.retrieved_at, scenario_id=scenario.scenario_id)
        for item in manifest.snapshots
    ]
    store.import_scenario(scenario, snapshots)
    return scenario


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a SkyWatch historical ADS-B scenario")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--agent-manifest", type=Path)
    args = parser.parse_args()
    try:
        store = Store(Settings().db_path)
        try:
            scenario = import_file(store, args.manifest, agent_manifest=args.agent_manifest)
        finally:
            store.close()
    except (ValueError, ValidationError, OSError, sqlite3.Error) as exc:
        parser.exit(2, f"Import failed: {exc}\n")
    provenance = "synthetic" if scenario.synthetic else "historical"
    print(f"Imported {provenance} scenario {scenario.scenario_id}")


if __name__ == "__main__":
    main()

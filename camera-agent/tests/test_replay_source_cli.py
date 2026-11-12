import json
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from skywatch_agent.main import main
from skywatch_agent.replay import load_scenarios
from skywatch_agent.source import VideoSource


def test_two_mp4s_preserve_recording_offsets_and_end_of_file(demo):
    _, scenarios = demo
    recordings = scenarios["synthetic-motion"].recordings
    timestamps = []
    for name in ("camera_1", "camera_2"):
        source = VideoSource(recording=recordings[name])
        frames = []
        try:
            while (frame := source.read()) is not None:
                frames.append(frame)
        finally:
            source.close()
        assert len(frames) == 80
        assert (frames[-1].captured_at - frames[0].captured_at).total_seconds() == pytest.approx(
            7.9
        )
        timestamps.append(frames[0].captured_at)
    assert (timestamps[1] - timestamps[0]).total_seconds() == 0.2


def test_explicit_variable_frame_timestamps(demo):
    _, scenarios = demo
    recording = scenarios["synthetic-motion"].recordings["camera_1"]
    source = VideoSource(recording=replace(recording, frame_offsets=(0, 0.04, 0.13)))
    try:
        assert [source.read().offset for _ in range(3)] == [0, 0.04, 0.13]
        with pytest.raises(ValueError, match="Missing original timestamp"):
            source.read()
    finally:
        source.close()


def test_live_capture_timestamp_and_device_failure(monkeypatch):
    released = []
    results = iter([(True, np.zeros((10, 10, 3))), (False, None)])
    fake = SimpleNamespace(
        isOpened=lambda: True,
        release=lambda: released.append(True),
        get=lambda _: 30,
        set=lambda *_: True,
        read=lambda: next(results),
    )
    monkeypatch.setattr(cv2, "VideoCapture", lambda _: fake)
    before = datetime.now(UTC)
    source = VideoSource(device=0)
    assert source.read().captured_at >= before
    with pytest.raises(OSError, match="stopped"):
        source.read()
    source.close()
    assert released


def test_scenario_rejects_duplicate_ids_and_bad_timestamps(demo, tmp_path):
    directory, _ = demo
    path = directory / "synthetic-motion.json"
    with pytest.raises(ValueError, match="duplicated"):
        load_scenarios((path, path))
    data = json.loads(path.read_text())
    data["cameras"]["camera_1"]["captured_start"] = "2026-01-01T12:00:00"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="UTC offset"):
        load_scenarios((bad,))


@pytest.mark.parametrize(
    "scenario,expectation,code",
    [
        ("synthetic-motion", "any", 0),
        ("synthetic-empty", "empty", 0),
        ("synthetic-motion", "airplane", 3),
        ("synthetic-motion", "empty", 3),
    ],
)
def test_offline_evaluation_is_honest_about_synthetic_data(
    demo, tmp_path, scenario, expectation, code
):
    directory, _ = demo
    output = tmp_path / "report.json"
    assert (
        main(
            [
                "evaluate",
                "--config",
                str(directory / "camera_1.toml"),
                "--scenario",
                scenario,
                "--output",
                str(output),
                "--expect",
                expectation,
            ]
        )
        == code
    )
    report = json.loads(output.read_text())
    assert report["material"] == "SIMULATED" and report["frames"] == 80
    assert (
        "airplane" not in report["observations_by_type"]
        or report["observations_by_type"]["airplane"] == 0
    )


def test_cli_bad_configuration_returns_nonzero(tmp_path):
    assert main(["run", "--config", str(tmp_path / "missing.toml")]) == 2

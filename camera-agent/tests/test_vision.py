from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from skywatch_agent.config import DetectorConfig, TrackerConfig
from skywatch_agent.detector import Detection, MotionDetector, YoloDetector
from skywatch_agent.pipeline import Pipeline
from skywatch_agent.source import Frame
from skywatch_agent.tracker import Tracker


def detection(x=0.2, kind="airplane"):
    return Detection(kind, 0.9, (x, 0.2, 0.03, 0.02))


def test_tracker_stable_ids_gap_expiry_and_class_separation():
    tracker = Tracker(TrackerConfig(min_hits=2, max_missed=2))
    assert tracker.update([detection()]) == []
    first = tracker.update([detection(0.21)])[0].track_id
    assert tracker.update([]) == []
    assert tracker.update([detection(0.23)])[0].track_id == first
    assert tracker.update([detection(0.24, "bird")]) == []
    assert tracker.update([detection(0.25, "bird")])[0].track_id != first
    tracker.update([])
    assert first not in tracker.tracks


def test_tracker_one_to_one_and_crossing():
    tracker = Tracker(TrackerConfig(min_hits=1))
    first = tracker.update([detection(0.2), detection(0.3)])
    ids = [track.track_id for track in first]
    tracker.update([detection(0.23), detection(0.27)])
    tracks = tracker.update([detection(0.26), detection(0.24)])
    assert len({t.track_id for t in tracks}) == 2
    assert tracker.tracks[ids[0]].detection.bbox[0] == 0.26
    assert tracker.tracks[ids[1]].detection.bbox[0] == 0.24


def test_yolo_decode_letterbox_nms_and_class_gating():
    detector = YoloDetector.__new__(YoloDetector)
    detector.config = DetectorConfig()
    predictions = np.zeros((1, 84, 5), dtype=np.float32)
    # Original 320x180; 640x640 letterbox has top=140 and scale=2.
    predictions[0, :4, :] = np.array(
        [
            [120, 120, 360, 480, 200],
            [240, 240, 300, 240, 250],
            [80, 80, 60, 80, 50],
            [40, 40, 40, 40, 30],
        ]
    )
    predictions[0, 8, :2] = [0.9, 0.8]  # duplicate airplane
    predictions[0, 18, 2] = 0.8  # bird
    predictions[0, 8, 3] = 0.6
    predictions[0, 4, 3] = 0.95  # person wins: do not emit an airplane
    predictions[0, 8, 4] = 0.1  # below threshold
    results = detector.decode(predictions, 320, 180, 2, 0, 140)
    assert [d.object_type for d in results] == ["airplane", "bird"]
    assert results[0].bbox == pytest.approx((40 / 320, 40 / 180, 40 / 320, 20 / 180))
    assert results[0].confidence == pytest.approx(0.9)


def test_yolo_clips_boxes_and_rejects_incompatible_model():
    detector = YoloDetector.__new__(YoloDetector)
    detector.config = DetectorConfig()
    predictions = np.zeros((1, 84, 1), dtype=np.float32)
    predictions[0, :4, 0] = [0, 0, 100, 100]
    predictions[0, 8, 0] = 0.9
    assert detector.decode(predictions, 100, 100, 1, 0, 0)[0].bbox == (0, 0, 0.5, 0.5)
    with pytest.raises(ValueError, match="Expected YOLO"):
        detector.decode(np.zeros((1, 300, 6)), 100, 100, 1, 0, 0)


def test_motion_warmup_empty_scene_and_moving_object():
    detector = MotionDetector(DetectorConfig(kind="motion", warmup_frames=5))
    blank = np.full((180, 320, 3), 180, dtype=np.uint8)
    for _ in range(20):
        assert detector.detect(blank) == []
    moving = blank.copy()
    moving[70:80, 40:60] = 0
    detections = detector.detect(moving)
    assert detections and all(d.object_type == "unknown" for d in detections)


def test_local_pretrained_yolo_inference_when_model_is_available():
    model = Path(__file__).parents[1] / "models/yolo11n.onnx"
    if not model.is_file():
        pytest.skip("Run scripts/prepare_model.py for the optional pretrained model smoke test")
    detector = YoloDetector(DetectorConfig(model=model))
    # Only checks real model loading/inference, not accuracy on a real sky recording.
    assert detector.detect(np.full((180, 320, 3), (210, 175, 130), dtype=np.uint8)) == []


@pytest.mark.parametrize("mode", ["live", "replay"])
def test_pipeline_throttles_by_capture_time_and_preserves_identity(mode):
    pipeline = Pipeline(
        "camera_1", SimpleNamespace(detect=lambda _: [detection()]), TrackerConfig(min_hits=1), 0.5
    )
    start = datetime(2020, 1, 1, tzinfo=UTC)
    scenario = "past" if mode == "replay" else None

    def frame(seconds):
        return Frame(np.zeros((10, 10, 3)), start + timedelta(seconds=seconds), seconds)

    first = pipeline.process(frame(0), mode, scenario)[0]
    assert pipeline.process(frame(0.1), mode, scenario) == []
    second = pipeline.process(frame(0.5), mode, scenario)[0]
    assert first["track_id"] == second["track_id"]
    assert first["observation_id"] != second["observation_id"]
    assert first["captured_at"] == "2020-01-01T00:00:00Z"
    assert first["scenario_id"] == scenario

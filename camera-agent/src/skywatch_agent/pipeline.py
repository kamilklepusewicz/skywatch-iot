from uuid import uuid4

from .contracts import timestamp, validate
from .tracker import Tracker


class Pipeline:
    """The exact same detector/tracker/serializer is used by LIVE, REPLAY and evaluation."""

    def __init__(self, camera_id, detector, tracker_config, observation_interval):
        self.camera_id = camera_id
        self.detector = detector
        self.tracker = Tracker(tracker_config)
        self.interval = observation_interval
        self.last_sent = {}

    def process(self, frame, mode, scenario_id=None):
        tracks = self.tracker.update(self.detector.detect(frame.image))
        self.last_sent = {k: v for k, v in self.last_sent.items() if k in self.tracker.tracks}
        observations = []
        for track in tracks:
            previous = self.last_sent.get(track.track_id)
            if (
                previous is not None
                and (frame.captured_at - previous).total_seconds() < self.interval
            ):
                continue
            observation = validate(
                "observation",
                {
                    "schema_version": 1,
                    "observation_id": uuid4().hex,
                    "camera_id": self.camera_id,
                    "captured_at": timestamp(frame.captured_at),
                    "object_type": track.detection.object_type,
                    "confidence": track.detection.confidence,
                    "bbox": list(track.detection.bbox),
                    "mode": mode,
                    "scenario_id": scenario_id,
                    "track_id": track.track_id,
                },
            )
            self.last_sent[track.track_id] = frame.captured_at
            observations.append(observation)
        return observations

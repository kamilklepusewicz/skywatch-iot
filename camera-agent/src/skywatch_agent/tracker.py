import math
from dataclasses import dataclass
from uuid import uuid4

from .config import TrackerConfig
from .detector import Detection


def center(box):
    x, y, w, h = box
    return x + w / 2, y + h / 2


@dataclass
class Track:
    track_id: str
    detection: Detection
    hits: int = 1
    missed: int = 0
    velocity: tuple[float, float] = (0, 0)


class Tracker:
    """Greedy one-to-one assignment with constant-velocity prediction and class gating."""

    def __init__(self, config: TrackerConfig):
        self.config = config
        self.tracks: dict[str, Track] = {}

    def update(self, detections: list[Detection]) -> list[Track]:
        candidates = []
        for key, track in self.tracks.items():
            x, y = center(track.detection.bbox)
            predicted = (
                x + track.velocity[0] * (track.missed + 1),
                y + track.velocity[1] * (track.missed + 1),
            )
            for i, detection in enumerate(detections):
                distance = math.dist(predicted, center(detection.bbox))
                if (
                    track.detection.object_type == detection.object_type
                    and distance <= self.config.max_distance
                ):
                    candidates.append((distance, key, i))
        used_tracks, used_detections = set(), set()
        for _, key, i in sorted(candidates):
            if key in used_tracks or i in used_detections:
                continue
            track = self.tracks[key]
            old, new = center(track.detection.bbox), center(detections[i].bbox)
            track.velocity = tuple((b - a) / (track.missed + 1) for a, b in zip(old, new))
            track.detection = detections[i]
            track.hits += 1
            track.missed = 0
            used_tracks.add(key)
            used_detections.add(i)
        for key in list(self.tracks):
            if key not in used_tracks:
                self.tracks[key].missed += 1
                if self.tracks[key].missed > self.config.max_missed:
                    del self.tracks[key]
        for i, detection in enumerate(detections):
            if i not in used_detections:
                key = uuid4().hex
                self.tracks[key] = Track(key, detection)
        return [t for t in self.tracks.values() if t.missed == 0 and t.hits >= self.config.min_hits]

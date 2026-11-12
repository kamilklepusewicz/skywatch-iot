import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import cv2
import numpy as np

from .replay import Recording


@dataclass(frozen=True)
class Frame:
    image: np.ndarray
    captured_at: datetime
    offset: float


class VideoSource:
    def __init__(self, device: int | str = 0, recording: Recording | None = None):
        self.recording = recording
        if recording and not recording.path.is_file():
            raise ValueError(f"Recording does not exist: {recording.path}")
        self.capture = cv2.VideoCapture(str(recording.path) if recording else device)
        if not self.capture.isOpened():
            self.capture.release()
            raise ValueError(
                "Cannot open recording/camera; check path, permissions and device index"
            )
        self.fps = float(self.capture.get(cv2.CAP_PROP_FPS))
        if recording and (not math.isfinite(self.fps) or self.fps <= 0):
            self.capture.release()
            raise ValueError("Recording has no usable FPS")
        if not recording:
            self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.index = 0
        self.previous_offset = -1.0
        self.first_pts = None

    def read(self) -> Frame | None:
        ok, image = self.capture.read()
        if not ok or image is None:
            if not self.recording:
                raise OSError("Live camera stopped providing frames")
            offsets = self.recording.frame_offsets
            if offsets is not None and self.index != len(offsets):
                raise ValueError("Frame timestamp count differs from decoded frame count")
            return None
        offset = 0.0
        captured_at = datetime.now(UTC)
        if self.recording:
            offsets = self.recording.frame_offsets
            if offsets is not None:
                if self.index >= len(offsets):
                    raise ValueError("Missing original timestamp for decoded frame")
                offset = offsets[self.index]
            else:
                pts = float(self.capture.get(cv2.CAP_PROP_POS_MSEC)) / 1000
                if self.first_pts is None:
                    self.first_pts = pts if math.isfinite(pts) and pts >= 0 else 0
                offset = pts - self.first_pts
                if not math.isfinite(offset) or offset <= self.previous_offset:
                    offset = max(self.index / self.fps, self.previous_offset + 1 / self.fps)
            captured_at = self.recording.captured_start + timedelta(seconds=offset)
        self.previous_offset = offset
        self.index += 1
        return Frame(image, captured_at, offset)

    def close(self) -> None:
        self.capture.release()

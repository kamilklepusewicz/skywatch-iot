"""CPU inference: YOLOv8/YOLO11 COCO ONNX or explicitly unclassified motion."""

from dataclasses import dataclass

import cv2
import numpy as np

from .config import DetectorConfig


@dataclass(frozen=True)
class Detection:
    object_type: str
    confidence: float
    bbox: tuple[float, float, float, float]


class YoloDetector:
    def __init__(self, config: DetectorConfig):
        self.config = config
        if config.model is None or not config.model.is_file():
            raise ValueError("Missing local YOLO ONNX model; see camera-agent/README.md")
        self.net = cv2.dnn.readNetFromONNX(str(config.model))
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

    def detect(self, image: np.ndarray) -> list[Detection]:
        height, width = image.shape[:2]
        size = self.config.image_size
        scale = min(size / width, size / height)
        resized = cv2.resize(image, (round(width * scale), round(height * scale)))
        top = (size - resized.shape[0]) // 2
        left = (size - resized.shape[1]) // 2
        padded = np.full((size, size, 3), 114, dtype=np.uint8)
        padded[top : top + resized.shape[0], left : left + resized.shape[1]] = resized
        self.net.setInput(cv2.dnn.blobFromImage(padded, 1 / 255, (size, size), swapRB=True))
        output = self.net.forward()
        return self.decode(output, width, height, scale, left, top)

    def decode(self, output, width, height, scale, left, top) -> list[Detection]:
        rows = np.asarray(output)
        if rows.ndim != 3 or rows.shape[0] != 1 or rows.shape[1] != 84:
            raise ValueError("Expected YOLOv8/11 COCO detection ONNX [1,84,N], nms=False")
        # Use the winning COCO class, never relabel another class as an airplane.
        rows = rows[0].T
        class_ids = rows[:, 4:].argmax(axis=1)
        confidence = rows[np.arange(len(rows)), class_ids + 4]
        detections = []
        for class_id, label in ((4, "airplane"), (14, "bird")):
            boxes, scores = [], []
            selected = rows[(class_ids == class_id) & (confidence >= self.config.confidence)]
            for row in selected:
                if not np.isfinite(row).all() or not 0 <= row[4 + class_id] <= 1:
                    continue
                cx, cy, w, h = row[:4]
                x1 = float(np.clip((cx - w / 2 - left) / scale, 0, width))
                y1 = float(np.clip((cy - h / 2 - top) / scale, 0, height))
                x2 = float(np.clip((cx + w / 2 - left) / scale, 0, width))
                y2 = float(np.clip((cy + h / 2 - top) / scale, 0, height))
                if x2 > x1 and y2 > y1:
                    boxes.append([x1, y1, x2 - x1, y2 - y1])
                    scores.append(float(row[4 + class_id]))
            indices = cv2.dnn.NMSBoxes(
                boxes,
                scores,
                self.config.confidence,
                self.config.nms_iou,
            )
            for i in np.asarray(indices).reshape(-1):
                x, y, w, h = boxes[i]
                detections.append(
                    Detection(label, scores[i], (x / width, y / height, w / width, h / height))
                )
        return detections


class MotionDetector:
    """Stationary-camera baseline. Motion is always unknown, never a claimed airplane."""

    def __init__(self, config: DetectorConfig):
        self.config = config
        self.background = cv2.createBackgroundSubtractorMOG2(
            history=300,
            varThreshold=25,
            detectShadows=False,
        )
        self.frames = 0

    def detect(self, image: np.ndarray) -> list[Detection]:
        mask = self.background.apply(image)
        self.frames += 1
        if self.frames <= self.config.warmup_frames:
            return []
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        height, width = image.shape[:2]
        result = []
        for contour in contours:
            area = cv2.contourArea(contour) / (width * height)
            if self.config.min_area <= area <= self.config.max_area:
                x, y, w, h = cv2.boundingRect(contour)
                # Foreground occupancy is a motion score, not a class probability.
                score = float(np.count_nonzero(mask[y : y + h, x : x + w])) / (w * h)
                if score >= self.config.confidence:
                    result.append(
                        Detection("unknown", score, (x / width, y / height, w / width, h / height))
                    )
        return result


def make_detector(config: DetectorConfig):
    return YoloDetector(config) if config.kind == "yolo" else MotionDetector(config)

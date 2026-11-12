"""Small generated MP4 fixtures, explicitly synthetic (not real sky footage)."""

import json
from pathlib import Path

import cv2
import numpy as np


def generate_demo(directory: Path) -> Path:
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("Demo output directory must be empty; refusing to overwrite existing data")
    directory.mkdir(parents=True, exist_ok=True)
    for name, shift in (("camera_1", 0), ("camera_2", 12), ("empty", None)):
        writer = cv2.VideoWriter(
            str(directory / f"{name}.mp4"),
            cv2.VideoWriter_fourcc(*"mp4v"),
            10,
            (320, 180),
        )
        if not writer.isOpened():
            raise OSError("OpenCV cannot create MP4 with mp4v codec")
        try:
            for i in range(80):
                frame = np.full((180, 320, 3), (210, 175, 130), dtype=np.uint8)
                if shift is not None and i >= 25:
                    x = 20 + (i - 25) * 4
                    cv2.rectangle(frame, (x, 70 + shift), (x + 16, 78 + shift), (20, 20, 20), -1)
                writer.write(frame)
        finally:
            writer.release()
    for scenario_id, empty in (("synthetic-motion", False), ("synthetic-empty", True)):
        data = {
            "scenario_id": scenario_id,
            "synthetic": True,
            "description": "Generated rectangles/flat background; NOT aircraft or real empty sky.",
            "cameras": {
                name: {
                    "video": "empty.mp4" if empty else f"{name}.mp4",
                    "captured_start": f"2026-01-01T12:00:00.{offset}Z",
                }
                for name, offset in (("camera_1", "000"), ("camera_2", "200"))
            },
        }
        (directory / f"{scenario_id}.json").write_text(json.dumps(data, indent=2) + "\n")
    for name in ("camera_1", "camera_2"):
        (directory / f"{name}.toml").write_text(
            f'camera_id = "{name}"\n'
            'scenario_files = ["synthetic-motion.json", "synthetic-empty.json"]\n'
            "observation_interval = 0.2\n"
            '\n[detector]\nkind = "motion"\nwarmup_frames = 20\n'
            "\n[tracker]\nmin_hits = 3\n"
        )
    return directory

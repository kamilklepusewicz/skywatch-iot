"""Optional loopback-only preview. JPEG frames never enter MQTT or persistent storage."""

import json
import logging
import math
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files

import cv2
import numpy as np

from .contracts import timestamp

LOG = logging.getLogger(__name__)


def jpeg(image):
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        raise ValueError("Cannot encode preview JPEG")
    return encoded.tobytes()


def placeholder(mode):
    image = np.full((405, 720, 3), (27, 20, 12), dtype=np.uint8)
    text = "IDLE - start LIVE or REPLAY" if mode == "idle" else "Waiting for frames..."
    cv2.putText(image, text, (35, 205), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (240, 240, 240), 2)
    return jpeg(image)


class PreviewServer:
    def __init__(self, camera_id, device, detector, port, *, max_fps=10):
        if not 0 <= port <= 65535:
            raise ValueError("Preview port must be between 0 and 65535")
        if not math.isfinite(max_fps) or max_fps <= 0:
            raise ValueError("Preview FPS must be positive and finite")
        self.condition = threading.Condition()
        self.state = {
            "camera_id": camera_id,
            "device": device,
            "detector": detector,
            "mode": "idle",
            "scenario_id": None,
            "captured_at": None,
            "width": None,
            "height": None,
            "error": None,
        }
        self.encoded = placeholder("idle")
        self.version = 0
        self.closed = False
        self.interval = 1 / max_fps
        self.last_frame_time = None
        self.next_frame_time = 0
        self.thread = None
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, message, *args):
                LOG.debug(message, *args)

            def setup(self):
                super().setup()
                self.connection.settimeout(3)

            def reply(self, content_type, body):
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                try:
                    path = self.path.split("?", 1)[0]
                    if path == "/":
                        self.reply(
                            "text/html; charset=utf-8",
                            files("skywatch_agent").joinpath("preview.html").read_bytes(),
                        )
                    elif path == "/preview.js":
                        self.reply(
                            "text/javascript; charset=utf-8",
                            files("skywatch_agent").joinpath("preview.js").read_bytes(),
                        )
                    elif path == "/status.json":
                        self.reply("application/json", json.dumps(owner.snapshot()).encode())
                    elif path == "/frame.jpg":
                        with owner.condition:
                            body = owner.encoded
                        self.reply("image/jpeg", body)
                    elif path == "/stream.mjpg":
                        self.stream()
                    else:
                        self.send_error(404)
                except (BrokenPipeError, ConnectionResetError, TimeoutError):
                    pass

            def stream(self):
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                version = -1
                while True:
                    with owner.condition:
                        owner.condition.wait_for(
                            lambda: owner.closed or owner.version != version,
                            timeout=1,
                        )
                        if owner.closed:
                            return
                        if owner.version == version:
                            continue
                        version, body = owner.version, owner.encoded
                    self.wfile.write(
                        b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                        + str(len(body)).encode()
                        + b"\r\n\r\n"
                        + body
                        + b"\r\n"
                    )
                    self.wfile.flush()

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def start(self):
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        LOG.info("Local camera preview: %s", self.url)

    def snapshot(self):
        with self.condition:
            return {
                **self.state,
                "frame_age_seconds": None
                if self.last_frame_time is None
                else time.monotonic() - self.last_frame_time,
            }

    def set_state(self, mode, scenario_id=None, *, error=None):
        # Clear old images on stop/source change so an idle camera never looks live.
        encoded = placeholder(mode)
        with self.condition:
            self.state.update(
                mode=mode,
                scenario_id=scenario_id,
                error=error,
                captured_at=None,
                width=None,
                height=None,
            )
            self.last_frame_time = None
            self.next_frame_time = 0
            self.encoded = encoded
            self.version += 1
            self.condition.notify_all()

    def error(self, message):
        with self.condition:
            self.state["error"] = message

    def update(self, frame, tracks):
        now = time.monotonic()
        if now < self.next_frame_time:
            return
        self.next_frame_time = now + self.interval
        original_height, original_width = frame.image.shape[:2]
        scale = min(1, 960 / original_width)
        image = cv2.resize(
            frame.image, (round(original_width * scale), round(original_height * scale))
        )
        height, width = image.shape[:2]
        for track in tracks:
            detection = track.detection
            x, y, w, h = detection.bbox
            left, top = round(x * width), round(y * height)
            right, bottom = round((x + w) * width), round((y + h) * height)
            cv2.rectangle(image, (left, top), (right, bottom), (120, 235, 150), 2)
            label = f"{detection.object_type} {detection.confidence:.0%} #{track.track_id[:6]}"
            cv2.putText(
                image,
                label,
                (left, max(16, top - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (120, 235, 150),
                1,
                cv2.LINE_AA,
            )
        encoded = jpeg(image)
        with self.condition:
            self.encoded = encoded
            self.state.update(
                captured_at=timestamp(frame.captured_at),
                width=original_width,
                height=original_height,
            )
            self.last_frame_time = now
            self.version += 1
            self.condition.notify_all()

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()
        if self.thread is not None:
            self.server.shutdown()
            self.thread.join(timeout=3)
        self.server.server_close()

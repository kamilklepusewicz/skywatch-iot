import json
import time
from datetime import UTC, datetime
from urllib.error import HTTPError
from urllib.request import urlopen

import cv2
import numpy as np
import pytest

from skywatch_agent.detector import Detection
from skywatch_agent.preview import PreviewServer
from skywatch_agent.source import Frame
from skywatch_agent.tracker import Track

pytestmark = pytest.mark.integration


@pytest.fixture
def preview():
    server = PreviewServer("camera_1", 2, "motion", 0)
    server.start()
    try:
        yield server
    finally:
        server.close()


def fetch(server, path):
    with urlopen(server.url + path, timeout=3) as response:
        return response.headers, response.read()


def test_preview_serves_local_frames_and_boxes_without_mutating_source(preview):
    assert preview.server.server_address[0] == "127.0.0.1"
    assert b"Podgl" in fetch(preview, "/")[1]
    assert fetch(preview, "/preview.js")[0]["Content-Type"].startswith("text/javascript")
    preview.set_state("live")
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    frame = Frame(image, datetime(2026, 1, 1, tzinfo=UTC), 0)
    track = Track("stable-track", Detection("unknown", 0.9, (0.2, 0.2, 0.3, 0.3)))
    preview.update(frame, [track])
    headers, body = fetch(preview, "/frame.jpg")
    assert headers["Content-Type"] == "image/jpeg" and headers["Cache-Control"] == "no-store"
    decoded = cv2.imdecode(np.frombuffer(body, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape == image.shape
    assert decoded[20, 40, 1] > 150  # Visible green box at normalized coordinates.
    assert not image.any()  # Overlays never enter the inference input.
    state = json.loads(fetch(preview, "/status.json")[1])
    assert state["mode"] == "live" and state["device"] == 2
    assert state["width"] == 200 and state["height"] == 100
    assert state["captured_at"] == "2026-01-01T00:00:00Z"
    with pytest.raises(HTTPError) as error:
        fetch(preview, "/missing")
    assert error.value.code == 404


def test_stop_removes_old_camera_image_and_exposes_capture_error(preview):
    preview.set_state("live")
    preview.update(Frame(np.full((40, 60, 3), 255, np.uint8), datetime.now(UTC), 0), [])
    live = fetch(preview, "/frame.jpg")[1]
    preview.set_state("idle")
    preview.error("Camera disconnected")
    state = json.loads(fetch(preview, "/status.json")[1])
    assert state["mode"] == "idle" and state["captured_at"] is None
    assert state["width"] is None and state["frame_age_seconds"] is None
    assert state["error"] == "Camera disconnected"
    assert fetch(preview, "/frame.jpg")[1] != live


def test_mjpeg_stream_delivers_new_frames_and_shutdown_releases_clients():
    preview = PreviewServer("camera_1", 2, "motion", 0)
    preview.start()
    stream = urlopen(preview.url + "/stream.mjpg", timeout=3)

    def read_frame():
        assert stream.readline() == b"--frame\r\n"
        assert stream.readline() == b"Content-Type: image/jpeg\r\n"
        size = int(stream.readline().split(b":")[1])
        assert stream.readline() == b"\r\n"
        body = stream.read(size)
        assert stream.read(2) == b"\r\n"
        return body

    try:
        first = read_frame()
        preview.set_state("live")
        assert read_frame() != first
        preview.update(Frame(np.zeros((40, 60, 3), np.uint8), datetime.now(UTC), 0), [])
        body = read_frame()
        assert cv2.imdecode(np.frombuffer(body, np.uint8), cv2.IMREAD_COLOR).shape == (40, 60, 3)
    finally:
        start = time.monotonic()
        preview.close()
        stream.close()
        assert time.monotonic() - start < 2

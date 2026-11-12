import logging
import queue
import threading
import time
from collections import OrderedDict
from datetime import UTC, datetime

from .contracts import parse_time, timestamp, validate
from .detector import make_detector
from .pipeline import Pipeline
from .source import VideoSource

LOG = logging.getLogger(__name__)


class Agent:
    def __init__(
        self,
        config,
        transport,
        scenarios,
        *,
        source_factory=VideoSource,
        detector_factory=make_detector,
    ):
        self.config = config
        self.transport = transport
        self.scenarios = scenarios
        self.source_factory = source_factory
        self.detector_factory = detector_factory
        self.mode = "idle"
        self.scenario_id = None
        self.source = None
        self.pipeline = None
        self.pending_frame = None
        self.replay_started = 0
        self.completed = OrderedDict()
        self.shutdown = threading.Event()

    def stop(self):
        if self.source is not None:
            self.source.close()
        self.source = self.pipeline = self.pending_frame = None
        self.mode, self.scenario_id = "idle", None
        self.transport.report_status(self.mode)

    def start(self, mode, scenario_id=None):
        if mode == "live" and self.mode == "live":
            return
        recording = None
        if mode == "replay":
            if not scenario_id or scenario_id not in self.scenarios:
                raise ValueError("Unknown or missing scenario_id")
            scenario = self.scenarios[scenario_id]
            recording = scenario.recordings.get(self.config.camera_id)
            if recording is None:
                raise ValueError("Scenario has no recording for this camera_id")
            if scenario.synthetic:
                LOG.warning(
                    "SIMULATED material: %s; not evidence of aircraft detection", scenario_id
                )
        elif mode != "live":
            raise ValueError("Mode must be live or replay")
        detector = self.detector_factory(self.config.detector)
        new_source = self.source_factory(device=self.config.live_device, recording=recording)
        try:
            first = new_source.read()
            if first is None:
                raise ValueError("Recording is empty or cannot be decoded")
        except Exception:
            new_source.close()
            raise
        # Commit the mode change only after successfully opening and reading the replacement.
        if self.source is not None:
            self.source.close()
        self.source = new_source
        self.pipeline = Pipeline(
            self.config.camera_id, detector, self.config.tracker, self.config.observation_interval
        )
        self.mode, self.scenario_id = mode, scenario_id if mode == "replay" else None
        self.pending_frame = first
        self.replay_started = time.monotonic()
        self.transport.report_status(self.mode, self.scenario_id)

    def handle_command(self, command):
        validate("command", command)
        if command["camera_id"] != self.config.camera_id:
            return
        command_id = command["command_id"]
        if command_id in self.completed:
            original, previous_ack = self.completed[command_id]
            if original == command:
                self.transport.ack(previous_ack)
                return
            accepted, message = False, "command_id was already used for a different payload"
        else:
            try:
                age = (datetime.now(UTC) - parse_time(command["issued_at"])).total_seconds()
                if age > self.config.command_max_age or age < -30:
                    raise ValueError("Command expired or issued_at is too far in the future")
                if command["command"] == "stop":
                    self.stop()
                else:
                    self.start(
                        command["command"].removeprefix("start_"), command.get("scenario_id")
                    )
                accepted, message = True, f"Agent mode: {self.mode}"
            except Exception as exc:
                LOG.exception("Command failed: %s", command_id)
                accepted, message = False, f"{type(exc).__name__}: {exc}"
        ack = validate(
            "ack",
            {
                "schema_version": 1,
                "command_id": command_id,
                "camera_id": self.config.camera_id,
                "reported_at": timestamp(),
                "accepted": accepted,
                "message": message,
            },
        )
        if command_id not in self.completed:
            self.completed[command_id] = (dict(command), ack)
            if len(self.completed) > 2048:
                self.completed.popitem(last=False)
        self.transport.ack(ack)

    def tick(self):
        # Bound work per iteration so a command flood cannot starve capture/status.
        for _ in range(20):
            try:
                command = self.transport.commands.get_nowait()
            except queue.Empty:
                break
            self.handle_command(command)
        if self.source is None:
            return
        try:
            frame = self.pending_frame
            if frame is None:
                frame = self.source.read()
                if frame is None:
                    LOG.info("REPLAY completed: %s", self.scenario_id)
                    self.stop()
                    return
                self.pending_frame = frame
            if (
                self.mode == "replay"
                and time.monotonic() < self.replay_started + frame.offset / self.config.replay_speed
            ):
                return
            for observation in self.pipeline.process(frame, self.mode, self.scenario_id):
                try:
                    self.transport.observation(observation)
                except BufferError:
                    LOG.error(
                        "Observation dropped: MQTT queue is full (%s)",
                        observation["observation_id"],
                    )
            self.pending_frame = None
        except Exception:
            LOG.exception("Capture/detection failed; returning to idle")
            self.stop()

    def run(self, initial_mode="idle", scenario_id=None):
        self.transport.start()
        try:
            if initial_mode != "idle":
                self.start(initial_mode, scenario_id)
            heartbeat = 0.0
            while not self.shutdown.is_set():
                self.tick()
                now = time.monotonic()
                if now >= heartbeat:
                    self.transport.report_status(self.mode, self.scenario_id)
                    heartbeat = now + self.config.heartbeat_seconds
                self.shutdown.wait(0.01)
        finally:
            self.stop()
            self.transport.close()

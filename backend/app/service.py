import asyncio
import json
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from math import isfinite
from queue import Empty
from typing import Literal
from uuid import uuid4

import httpx
from jsonschema import ValidationError as SchemaError
from pydantic import ValidationError

from .adsb import PollError, fetch_snapshot
from .config import Settings
from .database import Store, command_at, sqlite_busy
from .models import (
    Ack,
    AdsbTiming,
    AircraftView,
    Camera,
    CameraStatus,
    Command,
    CommandRequest,
    CommandResult,
    FeedState,
    Health,
    Mode,
    ObservationTiming,
    Snapshot,
    StoredObservation,
    TimingSettings,
)
from .mqtt import SUFFIXES, Broker, Message, contracts

LOG = logging.getLogger(__name__)
Resource = Literal["health", "cameras", "scenarios", "observations", "aircraft"]
EventKind = Literal["ready", "changed", "heartbeat"]
MESSAGE_RESOURCE: dict[str, Resource] = {
    "observations": "observations",
    "status": "cameras",
    "ack": "cameras",
}


def invalid_json_number(value: str) -> None:
    raise ValueError(f"Invalid JSON number: {value}")


def finite_json_float(value: str) -> float:
    parsed = float(value)
    if not isfinite(parsed):
        invalid_json_number(value)
    return parsed


class Service:
    def __init__(self, settings: Settings, store: Store, broker: Broker) -> None:
        self.settings = settings
        self.store = store
        self.broker = broker
        self.validators = contracts()
        self.listeners: set[asyncio.Queue[set[Resource]]] = set()
        self.adsb_last_error: str | None = None

    def changed(self, *resources: Resource) -> None:
        for queue in self.listeners:
            pending = queue.get_nowait() if queue.full() else set()
            queue.put_nowait(pending.union(resources))

    def observation_timing(self, item: StoredObservation) -> ObservationTiming | None:
        if item.mode != "live":
            return None
        delta = (item.received_at - item.captured_at).total_seconds()
        return ObservationTiming(
            receipt_minus_capture_seconds=delta,
            warning=abs(delta) >= self.settings.clock_warning_seconds,
        )

    def adsb_timing(self, snapshot: Snapshot | None) -> AdsbTiming | None:
        if snapshot is None or snapshot.retrieved_at is None:
            return None
        delta = (snapshot.retrieved_at - snapshot.source_at).total_seconds()
        return AdsbTiming(
            source_at=snapshot.source_at,
            retrieved_at=snapshot.retrieved_at,
            retrieval_minus_source_seconds=delta,
            warning=abs(delta) >= self.settings.clock_warning_seconds,
        )

    def health(self) -> Health:
        return Health(
            mqtt_connected=self.broker.connected.is_set(),
            mqtt_subscribed=self.broker.subscribed.is_set(),
            adsb_polling_enabled=self.settings.adsb_enabled and self.settings.origin is not None,
            adsb_last_error=self.adsb_last_error,
            timing=TimingSettings(
                poll_interval_seconds=self.settings.poll_interval,
                match_window_seconds=self.settings.match_window_seconds,
                max_position_age_seconds=self.settings.adsb_max_position_age_seconds,
                clock_warning_seconds=self.settings.clock_warning_seconds,
            ),
            adsb_timing=self.adsb_timing(self.store.nearest_snapshot("", None)),
        )

    def ingest(self, item: Message) -> None:
        parts = item.topic.split("/")
        if len(parts) != 4 or parts[:2] != ["skywatch", "cameras"] or parts[3] not in SUFFIXES:
            return
        camera_id, suffix = parts[2:]
        if item.retained and suffix != "status":
            LOG.warning("mqtt_retained_message_ignored topic=%s", item.topic)
            return
        try:
            payload = json.loads(
                item.payload,
                parse_constant=invalid_json_number,
                parse_float=finite_json_float,
            )
            self.validators[SUFFIXES[suffix]].validate(payload)
            if payload["camera_id"] != camera_id:
                LOG.warning("mqtt_camera_mismatch topic=%s", item.topic)
                return
            if suffix == "observations":
                updated = self.store.add_observation(
                    StoredObservation(**payload, received_at=item.received_at),
                )
            elif suffix == "status":
                updated = self.record_status(CameraStatus(**payload), item)
            else:
                updated = self.store.acknowledge(Ack(**payload), item.received_at)
        except (ValueError, SchemaError, ValidationError, RecursionError, OverflowError) as exc:
            LOG.warning("mqtt_invalid_message topic=%s error=%s", item.topic, type(exc).__name__)
            return
        if updated:
            self.changed(MESSAGE_RESOURCE[suffix])

    def record_status(self, status: CameraStatus, item: Message) -> bool:
        previous = self.store.camera_status(status.camera_id)
        heartbeat = previous[2] if previous else None
        if status.online:
            # An old retained heartbeat must never acquire a new lease when subscribed again.
            if item.retained and previous and previous[0].reported_at >= status.reported_at:
                return False
            if (
                previous
                and previous[0].online
                and status.reported_at <= previous[0].reported_at
                and item.received_at - previous[1]
                < timedelta(seconds=self.settings.heartbeat_timeout_seconds)
            ):
                return False
            heartbeat = min(item.received_at, status.reported_at)
        # An offline packet, including an LWT generated at agent startup, takes effect on receipt.
        self.store.save_status(status, item.received_at, heartbeat)
        return True

    def cameras(self, now: datetime, *, include_commands: bool = True) -> list[Camera]:
        cameras = []
        ids = set(self.settings.camera_ids) | set(self.store.camera_ids())
        can_observe = not self.settings.mqtt_enabled or self.broker.subscribed.is_set()
        for camera_id in sorted(ids):
            camera = Camera(
                camera_id=camera_id,
                online=False,
                location=self.settings.camera_locations.get(camera_id),
                latest_command=command_at(self.store.latest_command(camera_id), now)
                if include_commands
                else None,
            )
            saved = self.store.camera_status(camera_id)
            if saved:
                state, received, heartbeat = saved
                camera.online = bool(
                    can_observe
                    and state.online
                    and heartbeat
                    and (now - heartbeat).total_seconds() < self.settings.heartbeat_timeout_seconds
                )
                camera.mode = state.mode
                camera.scenario_id = state.scenario_id
                camera.last_heartbeat_at = heartbeat
                camera.status_received_at = received
            cameras.append(camera)
        return cameras

    def issue(self, camera_id: str, body: CommandRequest, now: datetime) -> CommandResult:
        command = Command(
            command_id=str(uuid4()),
            camera_id=camera_id,
            issued_at=now,
            **body.model_dump(),
        )
        self.validators["command"].validate(command.model_dump(mode="json"))
        result = CommandResult(
            **command.model_dump(),
            status="pending",
            deadline_at=now + timedelta(seconds=self.settings.command_timeout_seconds),
        )
        self.store.save_command(result)
        status = self.broker.publish(command)
        if status != "pending":
            updated = result.model_copy(update={"status": status})
            try:
                self.store.save_command(updated)
            except sqlite3.Error as exc:
                # The durable pending state remains conservative if a later write loses the lock.
                if not sqlite_busy(exc):
                    raise
                LOG.warning("sqlite_busy operation=record_publish command_id=%s", result.command_id)
            else:
                result = updated
        self.changed("cameras")
        return result

    def aircraft(self, mode: Mode, scenario_id: str | None, at: datetime | None) -> AircraftView:
        scenario = self.store.scenario(scenario_id) if mode == "replay" and scenario_id else None
        reference = at if mode == "replay" else at or datetime.now(UTC)
        key = scenario.scenario_id if scenario else ""
        snapshot = self.store.nearest_snapshot(key, at) if mode == "live" or scenario else None
        status: FeedState = "unavailable"
        if snapshot is not None:
            stale = reference is not None and (
                abs((snapshot.source_at - reference).total_seconds())
                > self.settings.match_window_seconds
            )
            status = "stale" if stale else "available"
        return AircraftView(
            mode=mode,
            scenario_id=scenario_id,
            status=status,
            snapshot=snapshot,
            origin=scenario.origin
            if scenario
            else self.settings.origin
            if mode == "live"
            else None,
            synthetic=scenario.synthetic if scenario else False,
        )

    async def process(self) -> None:
        last_broker = self.broker.connected.is_set(), self.broker.subscribed.is_set()
        last_online: tuple[tuple[str, bool], ...] = ()
        last_stale = False
        last_version = self.store.db.execute("PRAGMA data_version").fetchone()[0]
        next_tick = 0.0
        loop = asyncio.get_running_loop()
        deferred: Message | None = None
        retries = 0
        retry_at = 0.0
        while True:
            for _ in range(128):
                if deferred and loop.time() < retry_at:
                    break
                try:
                    item = deferred or self.broker.messages.get_nowait()
                except Empty:
                    break
                try:
                    self.ingest(item)
                except sqlite3.Error as exc:
                    if sqlite_busy(exc) and retries < 20:
                        if retries == 0:
                            LOG.warning("sqlite_busy operation=mqtt_ingest topic=%s", item.topic)
                        deferred = item
                        retries += 1
                        retry_at = loop.time() + 0.5
                        break
                    LOG.exception(
                        "mqtt_persistence_failed topic=%s retries=%s", item.topic, retries
                    )
                deferred = None
                retries = 0

            if loop.time() >= next_tick:
                next_tick = loop.time() + 1
                now = datetime.now(UTC)
                broker = self.broker.connected.is_set(), self.broker.subscribed.is_set()
                online = tuple(
                    (c.camera_id, c.online) for c in self.cameras(now, include_commands=False)
                )
                version = self.store.db.execute("PRAGMA data_version").fetchone()[0]
                try:
                    expired = self.store.expire_commands(now)
                except sqlite3.Error as exc:
                    if not sqlite_busy(exc):
                        LOG.exception("sqlite_failure operation=expire_commands")
                        raise
                    LOG.warning("sqlite_busy operation=expire_commands")
                    expired = False
                if broker != last_broker:
                    self.changed("health", "cameras")
                    last_broker = broker
                if expired or online != last_online:
                    self.changed("cameras")
                    last_online = online
                if version != last_version:
                    self.changed("scenarios", "observations", "aircraft", "health")
                    last_version = version
                source = self.store.live_source_timestamp()
                stale = source is not None and (
                    abs(source - now.timestamp()) > self.settings.match_window_seconds
                )
                if stale != last_stale:
                    self.changed("aircraft")
                    last_stale = stale
            await asyncio.sleep(0.1 if deferred or self.broker.messages.empty() else 0)

    async def save_live_snapshot(self, snapshot: Snapshot) -> bool:
        cutoff = (snapshot.retrieved_at or datetime.now(UTC)) - timedelta(
            hours=self.settings.adsb_live_retention_hours
        )
        # Retrying a write here never repeats the HTTP request or consumes the API quota.
        for delay in (1, 2, 4, 0):
            try:
                self.store.save_snapshot(snapshot, keep_since=cutoff)
            except sqlite3.Error as exc:
                if not sqlite_busy(exc):
                    LOG.exception("sqlite_failure operation=save_adsb_snapshot")
                    raise
                if delay == 0:
                    LOG.error("sqlite_busy operation=save_adsb_snapshot snapshot_dropped=true")
                    return False
                LOG.warning("sqlite_busy operation=save_adsb_snapshot retry_seconds=%s", delay)
                await asyncio.sleep(delay)
            else:
                return True
        return False

    async def poll_flights(self) -> None:
        origin = self.settings.origin
        if not self.settings.adsb_enabled or origin is None:
            return
        key = self.settings.adsb_api_key
        headers = {"x-api-key": key.get_secret_value()} if key else {}
        period = self.settings.poll_interval
        delay = period
        async with httpx.AsyncClient(
            timeout=self.settings.adsb_timeout_seconds, headers=headers
        ) as http:
            while True:
                try:
                    snapshot = await fetch_snapshot(http, origin, self.settings.adsb_radius_nm)
                except PollError as exc:
                    self.adsb_last_error = str(exc)
                    LOG.warning("adsb_poll_failed error=%s", exc)
                    delay = max(period, min(900, delay * 2), exc.retry_after or 0)
                else:
                    timing = self.adsb_timing(snapshot)
                    if timing and timing.warning:
                        LOG.warning(
                            "adsb_time_difference source_at=%s retrieved_at=%s delta_seconds=%.1f",
                            timing.source_at,
                            timing.retrieved_at,
                            timing.retrieval_minus_source_seconds,
                        )
                    saved = await self.save_live_snapshot(snapshot)
                    self.adsb_last_error = (
                        None if saved else "SQLite busy while storing ADS-B snapshot"
                    )
                    delay = period
                    if saved:
                        self.changed("observations", "aircraft")
                self.changed("health")
                await asyncio.sleep(delay)

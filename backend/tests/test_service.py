import json
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.config import Settings
from app.database import Store
from app.main import create_app
from app.models import CommandRequest
from app.mqtt import Broker, Message
from app.service import Service

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "shared" / "examples"
NOW = datetime(2026, 1, 2, 12, tzinfo=UTC)


def sample(name, **fields):
    return json.loads((EXAMPLES / f"{name}.json").read_text(encoding="utf-8")) | fields


def deliver(service, suffix, payload, *, retained=False, at=NOW, topic_id=None):
    service.ingest(
        Message(
            f"skywatch/cameras/{topic_id or payload['camera_id']}/{suffix}",
            json.dumps(payload).encode(),
            retained,
            at,
        )
    )


def test_observations_and_restart(tmp_path):
    settings = Settings(database_path=tmp_path / "test.sqlite3", mqtt_enabled=False)
    with TestClient(create_app(settings)) as client:
        service = client.app.state.service
        first = sample("observation", camera_id="camera_1", observation_id="one")
        second = sample("observation", camera_id="camera_2", observation_id="two")
        client.portal.call(deliver, service, "observations", first | {"confidence": True})
        client.portal.call(partial(deliver, service, "observations", first, topic_id="camera_2"))
        client.portal.call(
            service.ingest,
            Message("skywatch/cameras/camera_1/observations", b"{", False, NOW),
        )
        assert client.get("/api/observations").json() == []
        client.portal.call(deliver, service, "observations", first)
        client.portal.call(
            partial(
                deliver,
                service,
                "observations",
                first,
                at=NOW + timedelta(seconds=5),
            )
        )
        client.portal.call(deliver, service, "observations", second)
        rows = client.get("/api/observations").json()
        assert {(x["camera_id"], x["observation_id"]) for x in rows} == {
            ("camera_1", "one"),
            ("camera_2", "two"),
        }
        saved = client.get("/api/observations/one").json()
        assert saved["received_at"] == "2026-01-02T12:00:00Z"
        assert saved["captured_at"] != saved["received_at"]
        assert client.get("/api/observations/missing").status_code == 404
        assert (
            client.get("/api/observations?camera_id=camera_2").json()[0]["observation_id"] == "two"
        )
        assert client.get("/api/health").json()["mqtt_connected"] is False
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/observations/one").json() == saved


def test_retained_heartbeat_and_lwt(tmp_path):
    settings = Settings(database_path=tmp_path / "test.sqlite3", mqtt_enabled=False)
    store = Store(settings.db_path)
    try:
        service = Service(settings, store, Broker(settings))
        online = sample(
            "camera-status",
            camera_id="camera_1",
            mode="live",
            online=True,
            reported_at=(NOW - timedelta(minutes=10)).isoformat(),
        )
        deliver(service, "status", online, retained=True)
        assert not service.cameras(NOW)[0].online
        fresh = online | {"reported_at": NOW.isoformat()}
        deliver(service, "status", fresh)
        assert service.cameras(NOW)[0].online
        assert not service.cameras(NOW)[1].online
        future = NOW + timedelta(minutes=2)
        deliver(service, "status", fresh, retained=True, at=future)
        assert not service.cameras(future)[0].online
        deliver(
            service,
            "status",
            online | {"online": False, "mode": "idle"},
            at=NOW + timedelta(seconds=1),
        )
        camera = service.cameras(NOW + timedelta(seconds=1))[0]
        assert not camera.online
        assert camera.mode == "idle"
        assert camera.last_heartbeat_at == NOW
    finally:
        store.close()


def test_commands_record_before_publish_and_track_first_ack(tmp_path, monkeypatch):
    settings = Settings(database_path=tmp_path / "test.sqlite3", mqtt_enabled=False)
    store = Store(settings.db_path)
    broker = Broker(settings)
    broker.subscribed.set()
    service = Service(settings, store, broker)

    def publish(topic, payload, *, qos, retain):
        command = json.loads(payload)
        assert topic == "skywatch/cameras/camera_1/commands"
        assert qos == 1 and retain is False
        assert store.command(command["command_id"]).status == "pending"
        assert command["schema_version"] == 1
        return SimpleNamespace(rc=0)

    monkeypatch.setattr(broker.client, "publish", publish)
    try:
        result = service.issue("camera_1", CommandRequest(command="stop"), NOW)
        assert result.status == "pending"
        ack = sample("ack", command_id=result.command_id, camera_id="camera_2", accepted=True)
        deliver(service, "ack", ack)
        assert store.command(result.command_id).ack is None
        deadline = result.deadline_at
        assert store.expire_commands(deadline)
        assert store.command(result.command_id).status == "timed_out"
        ack["camera_id"] = "camera_1"
        deliver(service, "ack", ack, at=deadline + timedelta(seconds=1))
        deliver(service, "ack", ack | {"accepted": False}, at=deadline + timedelta(seconds=2))
        saved = store.command(result.command_id)
        assert saved.status == "accepted" and saved.late
        assert saved.ack_received_at == deadline + timedelta(seconds=1)
        rejected = service.issue("camera_1", CommandRequest(command="start_live"), NOW)
        deliver(service, "ack", ack | {"command_id": rejected.command_id, "accepted": False})
        assert store.command(rejected.command_id).status == "rejected"
        broker.subscribed.clear()
        assert (
            service.issue("camera_1", CommandRequest(command="stop"), NOW).status
            == "publish_failed"
        )
    finally:
        store.close()


def test_api_validation_and_socket(tmp_path):
    settings = Settings(database_path=tmp_path / "test.sqlite3", mqtt_enabled=False)
    with TestClient(create_app(settings)) as client:
        with client.websocket_connect("/ws") as socket:
            assert socket.receive_json() == {"type": "ready"}
            assert (
                client.post("/api/cameras/missing/commands", json={"command": "stop"}).status_code
                == 404
            )
            assert (
                client.post(
                    "/api/cameras/camera_1/commands", json={"command": "start_replay"}
                ).status_code
                == 422
            )
            assert client.get("/api/aircraft?mode=replay").status_code == 422
            answer = client.post("/api/cameras/camera_1/commands", json={"command": "stop"})
            assert answer.status_code == 202
            assert socket.receive_json() == {"type": "changed", "resources": ["cameras"]}
            result = answer.json()
            assert result["status"] == "publish_failed"
            assert client.get(f"/api/commands/{result['command_id']}").json() == result


def test_paho_no_connection_during_publish_is_uncertain(tmp_path, monkeypatch):
    import paho.mqtt.client as paho

    settings = Settings(database_path=tmp_path / "race.sqlite3", mqtt_enabled=False)
    store = Store(settings.db_path)
    try:
        broker = Broker(settings)
        service = Service(settings, store, broker)
        broker.subscribed.set()
        result = service.issue("camera_1", CommandRequest(command="stop"), NOW)
        assert result.status == "delivery_uncertain"
        assert store.command(result.command_id).status == "delivery_uncertain"

        # Use Paho's real publish path without a socket. It buffers QoS 1 even with NO_CONN.
        (queued,) = broker.client._out_messages.values()
        assert json.loads(queued.payload)["command_id"] == result.command_id
        broker.subscribed.clear()
        assert store.expire_commands(result.deadline_at)
        assert store.command(result.command_id).status == "timed_out"
        ack = sample("ack", command_id=result.command_id, camera_id="camera_1", accepted=True)
        deliver(service, "ack", ack, at=result.deadline_at + timedelta(seconds=1))
        assert store.command(result.command_id).late
        broker.subscribed.set()
        monkeypatch.setattr(
            broker.client, "publish", lambda *a, **kw: SimpleNamespace(rc=paho.MQTT_ERR_QUEUE_SIZE)
        )
        rejected = service.issue("camera_1", CommandRequest(command="stop"), NOW)
        assert rejected.status == "publish_failed"
    finally:
        store.close()


def test_strict_numeric_observation_ingress(tmp_path):
    settings = Settings(database_path=tmp_path / "strict.sqlite3", mqtt_enabled=False)
    with TestClient(create_app(settings)) as client:
        service = client.app.state.service
        item = sample("observation", camera_id="camera_1", observation_id="invalid")
        for box in ([float("nan"), 0, 1, 1], [float("inf"), 0, 1, 1], [-0.1, 0, 1, 1]):
            client.portal.call(deliver, service, "observations", item | {"bbox": box})
        with_overflow = json.dumps(item | {"bbox": [float("inf"), 0, 1, 1]})
        client.portal.call(
            service.ingest,
            Message(
                "skywatch/cameras/camera_1/observations",
                with_overflow.replace("Infinity", "1e999").encode(),
                False,
                NOW,
            ),
        )
        assert client.get("/api/observations").json() == []


def test_keyset_page_survives_new_arrivals(tmp_path):
    settings = Settings(database_path=tmp_path / "pages.sqlite3", mqtt_enabled=False)
    with TestClient(create_app(settings)) as client:
        service = client.app.state.service
        for ident in ("a", "b", "c"):
            document = sample(
                "observation",
                observation_id=ident,
                camera_id="camera_1",
                mode="replay",
                scenario_id="chosen",
            )
            client.portal.call(deliver, service, "observations", document)
        endpoint = "/api/observations?scenario_id=chosen"
        page = client.get(endpoint + "&limit=2").json()
        assert [x["observation_id"] for x in page] == ["c", "b"]
        document = sample(
            "observation",
            observation_id="d",
            camera_id="camera_1",
            mode="replay",
            scenario_id="chosen",
        )
        client.portal.call(
            partial(deliver, service, "observations", document, at=NOW + timedelta(seconds=1))
        )
        older = client.get(endpoint + "&limit=2&before=b").json()
        assert [x["observation_id"] for x in older] == ["a"]


def test_periodic_writes_recover_from_external_lock(tmp_path, monkeypatch, caplog):
    import asyncio
    import sqlite3

    import pytest

    from app.models import CommandResult, Snapshot

    settings = Settings(
        database_path=tmp_path / "busy.sqlite3",
        mqtt_enabled=False,
        adsb_latitude=52,
        adsb_longitude=21,
        adsb_live_retention_hours=1,
    )
    store = Store(settings.db_path)
    store.db.execute("PRAGMA busy_timeout=0")
    service = Service(settings, store, Broker(settings))
    expired = CommandResult(
        command_id="due",
        camera_id="camera_1",
        command="stop",
        issued_at=NOW,
        deadline_at=NOW + timedelta(seconds=1),
        status="pending",
    )
    store.save_command(expired)
    old = Snapshot(source_at=NOW - timedelta(hours=2), retrieved_at=NOW, aircraft=[])
    fresh = Snapshot(source_at=NOW, retrieved_at=NOW, aircraft=[])
    store.save_snapshot(old)

    async def fetch(*args):
        return fresh

    monkeypatch.setattr("app.service.fetch_snapshot", fetch)
    external = sqlite3.connect(settings.db_path)

    async def exercise():
        external.execute("BEGIN IMMEDIATE")
        due = asyncio.create_task(service.process())
        adsb = asyncio.create_task(service.poll_flights())
        item = sample("observation", camera_id="camera_1", observation_id="deferred")
        service.broker.messages.put_nowait(
            Message("skywatch/cameras/camera_1/observations", json.dumps(item).encode(), False, NOW)
        )
        try:
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(0.6):
                    while True:
                        assert not due.done() and not adsb.done()
                        assert service.cameras(NOW)[0].camera_id == "camera_1"
                        assert store.command("due").status == "pending"
                        assert store.nearest_snapshot("", None) == old
                        assert store.observation("deferred") is None
                        await asyncio.sleep(0.05)
            external.rollback()
            async with asyncio.timeout(4):
                while (
                    store.command("due").status != "timed_out"
                    or store.nearest_snapshot("", None) != fresh
                    or store.observation("deferred") is None
                ):
                    await asyncio.sleep(0.05)
            assert store.snapshots_between("", old.source_at.timestamp(), NOW.timestamp()) == [
                fresh
            ]
            assert "sqlite_busy" in caplog.text
        finally:
            due.cancel()
            adsb.cancel()
            await asyncio.gather(due, adsb, return_exceptions=True)

    try:
        asyncio.run(exercise())
    finally:
        external.close()
        store.close()


def test_time_diagnostics_preserve_source_and_position_timestamps(tmp_path):
    from app.models import Snapshot

    settings = Settings(
        database_path=tmp_path / "timing.sqlite3",
        mqtt_enabled=False,
        adsb_enabled=False,
        adsb_latitude=52,
        adsb_longitude=21,
        adsb_poll_seconds=5,
        clock_warning_seconds=10,
    )
    retrieved = NOW + timedelta(seconds=45)
    with TestClient(create_app(settings)) as client:
        service = client.app.state.service
        snap = Snapshot(source_at=NOW, retrieved_at=retrieved, aircraft=[])
        client.portal.call(service.store.save_snapshot, snap)
        item = sample(
            "observation",
            camera_id="camera_1",
            observation_id="late-frame",
            captured_at=NOW.isoformat(),
            mode="live",
        )
        client.portal.call(partial(deliver, service, "observations", item, at=retrieved))
        health = client.get("/api/health").json()
        assert health["timing"]["poll_interval_seconds"] == 180
        assert health["timing"]["match_window_seconds"] == 35
        assert health["adsb_timing"]["retrieval_minus_source_seconds"] == 45
        assert health["adsb_timing"]["warning"] is True
        detail = client.get("/api/observations/late-frame").json()
        assert detail["timing"] == {"receipt_minus_capture_seconds": 45, "warning": True}
        item["mode"] = "replay"
        item["observation_id"] = "history-frame"
        client.portal.call(partial(deliver, service, "observations", item, at=retrieved))
        assert client.get("/api/observations/history-frame").json()["timing"] is None


def test_locked_database_rejects_command_before_publishing(tmp_path):
    import sqlite3

    settings = Settings(database_path=tmp_path / "busy-api.sqlite3", mqtt_enabled=False)
    with TestClient(create_app(settings)) as client:
        external = sqlite3.connect(settings.db_path)
        try:
            external.execute("BEGIN IMMEDIATE")
            response = client.post("/api/cameras/camera_1/commands", json={"command": "stop"})
            assert response.status_code == 503
            assert client.get("/api/cameras").json()[0]["latest_command"] is None
            external.rollback()
            assert (
                client.post("/api/cameras/camera_1/commands", json={"command": "stop"}).status_code
                == 202
            )
        finally:
            external.close()


def test_corrupt_legacy_observation_does_not_break_history(tmp_path):
    settings = Settings(database_path=tmp_path / "legacy.sqlite3", mqtt_enabled=False)
    with TestClient(create_app(settings)) as client:
        service = client.app.state.service

        def seed():
            item = sample(
                "observation",
                camera_id="camera_1",
                observation_id="legacy",
                bbox=[None, 0, 0, 0],
                received_at=NOW.isoformat(),
            )
            with service.store.db:
                service.store.db.execute(
                    "INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?)",
                    ("legacy", "camera_1", "live", None, NOW.timestamp(), json.dumps(item)),
                )
            deliver(
                service,
                "observations",
                sample("observation", observation_id="valid", camera_id="camera_1"),
            )

        client.portal.call(seed)
        assert [x["observation_id"] for x in client.get("/api/observations").json()] == ["valid"]
        assert client.get("/api/observations/legacy").status_code == 409
        assert client.portal.call(service.store.has_observation, "legacy")

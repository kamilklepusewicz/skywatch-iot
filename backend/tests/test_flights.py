from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.adsb import PollError, fetch_snapshot, normalize
from app.config import Settings
from app.database import Store
from app.matching import match
from app.models import Coordinates, Observation, Scenario

AT = datetime(2026, 1, 2, 12, tzinfo=UTC)
ORIGIN = Coordinates(latitude=52, longitude=21)


def snapshot(**aircraft):
    return {
        "now": AT.timestamp() * 1000,
        "ac": [
            {
                "hex": "abc123",
                "lat": 52.01,
                "lon": 21.01,
                "seen_pos": 4,
                "flight": " TEST123 ",
                "alt_baro": 2400,
                "alt_geom": 2700,
            }
            | aircraft
        ],
    }


def test_normalization():
    result = normalize(snapshot(alt_baro="ground", t="C172"), AT)
    assert result.source_at == AT
    (aircraft,) = result.aircraft
    assert aircraft.position_at == AT - timedelta(seconds=4)
    assert aircraft.callsign == "TEST123"
    assert aircraft.aircraft_type == "C172"
    assert aircraft.on_ground is True
    assert aircraft.altitude_baro_ft is None
    assert aircraft.altitude_geom_ft == 2700
    assert normalize(snapshot(seen_pos=None), AT).aircraft[0].position_at is None
    assert normalize(snapshot(lat=float("nan")), AT).aircraft == []


def test_http_errors_and_retry_after():
    import asyncio

    async def run():
        for code, expected in [(429, 900), (503, None), (401, None)]:

            def handle(request, code=code):
                assert request.url.path == "/v2/point/52.0/21.0/30"
                return httpx.Response(code, headers={"Retry-After": "900"})

            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                with pytest.raises(PollError) as failure:
                    await fetch_snapshot(client, ORIGIN, 30)
                assert failure.value.retry_after == expected

    asyncio.run(run())


def test_replay_matches_only_its_scenario_and_frame_time(tmp_path):
    settings = Settings(
        database_path=tmp_path / "test.sqlite3", camera_locations={"camera_1": ORIGIN}
    )
    observation = Observation(
        observation_id="o",
        camera_id="camera_1",
        captured_at=AT,
        object_type="airplane",
        confidence=0.9,
        bbox=(0, 0, 0.1, 0.1),
        mode="replay",
        scenario_id="history",
    )
    store = Store(settings.database_path)
    try:
        store.save_snapshot(normalize(snapshot(hex="aaa111"), AT))
        assert match(store, settings, observation).status == "unavailable"
        assert (
            match(store, settings, observation.model_copy(update={"mode": "live"})).status == "one"
        )
        store.import_scenario(
            Scenario(scenario_id="other", synthetic=False),
            [
                normalize(snapshot(hex="bbb222"), AT, scenario_id="other"),
            ],
        )
        assert match(store, settings, observation).status == "unavailable"
        store.import_scenario(
            Scenario(scenario_id="history", synthetic=True, cameras={"camera_1": ORIGIN}),
            [
                normalize(snapshot(hex="ccc333"), AT + timedelta(days=1), scenario_id="history"),
            ],
        )
        result = match(store, settings, observation)
        assert result.status == "one"
        assert result.synthetic
        assert result.candidates[0].aircraft.address == "ccc333"
        later = observation.model_copy(update={"captured_at": AT + timedelta(hours=1)})
        assert match(store, settings, later).status == "stale"
        bird = observation.model_copy(update={"object_type": "bird"})
        assert match(store, settings, bird).status == "skipped"
        store.import_scenario(
            Scenario(scenario_id="history", synthetic=True, cameras={"camera_1": ORIGIN}),
            [
                normalize(snapshot(lon=24), AT, scenario_id="history"),
            ],
        )
        assert match(store, settings, observation).status == "none"
    finally:
        store.close()


def test_ranking_uses_position_time_and_distance(tmp_path):
    settings = Settings(
        database_path=tmp_path / "test.sqlite3", camera_locations={"camera_1": ORIGIN}
    )
    store = Store(settings.db_path)
    observation = Observation(
        observation_id="rank",
        camera_id="camera_1",
        captured_at=AT,
        object_type="airplane",
        confidence=0.5,
        bbox=(0, 0, 0.1, 0.1),
        mode="live",
    )
    rows = [
        snapshot(hex="aaa111", lat=52.03, seen_pos=1)["ac"][0],
        snapshot(hex="bbb222", lat=52.01, seen_pos=1)["ac"][0],
        snapshot(hex="ccc333", lat=52.001, seen_pos=8)["ac"][0],
        snapshot(hex="ddd444", alt_baro="ground")["ac"][0],
        snapshot(hex="eee555", seen_pos=None)["ac"][0],
        snapshot(hex="fff666", seen_pos=40)["ac"][0],
    ]
    try:
        store.save_snapshot(normalize({"now": AT.timestamp() * 1000, "ac": rows}, AT))
        result = match(store, settings, observation)
        assert result.status == "multiple"
        assert [x.aircraft.address for x in result.candidates] == ["bbb222", "aaa111", "ccc333"]
        store.save_snapshot(normalize(snapshot(seen_pos=None), AT))
        assert match(store, settings, observation).reason == "positions_missing"
        store.save_snapshot(normalize(snapshot(seen_pos=40), AT))
        assert match(store, settings, observation).status == "stale"
    finally:
        store.close()


def test_locations_are_camera_specific_with_inclusive_distance_limit(tmp_path):
    from app.matching import distance_km

    settings = Settings(
        database_path=tmp_path / "locations.sqlite3",
        adsb_latitude=52,
        adsb_longitude=21,
        camera_locations={"near": ORIGIN, "far": Coordinates(latitude=53, longitude=21)},
    )
    obs = Observation(
        observation_id="location",
        camera_id="near",
        captured_at=AT,
        object_type="airplane",
        confidence=0.9,
        bbox=(0, 0, 0.1, 0.1),
        mode="live",
    )
    store = Store(settings.db_path)
    try:
        live = normalize(snapshot(), AT)
        store.save_snapshot(live)
        assert match(store, settings, obs.model_copy(update={"camera_id": "missing"})).reason == (
            "camera_location_missing"
        )
        assert match(store, settings, obs.model_copy(update={"camera_id": "far"})).status == "none"
        distance = distance_km(ORIGIN, live.aircraft[0])
        assert match(
            store, settings.model_copy(update={"match_radius_km": distance}), obs
        ).status == ("one")
        assert match(
            store, settings.model_copy(update={"match_radius_km": distance - 0.001}), obs
        ).status == ("none")
        store.import_scenario(
            Scenario(
                scenario_id="moved",
                synthetic=True,
                origin=ORIGIN,
                cameras={"far": ORIGIN, "near": None},
            ),
            [normalize(snapshot(), AT, scenario_id="moved")],
        )
        replay = obs.model_copy(update={"mode": "replay", "scenario_id": "moved"})
        assert match(store, settings, replay).reason == "camera_location_missing"
        assert (
            match(store, settings, replay.model_copy(update={"camera_id": "far"})).status == "one"
        )
    finally:
        store.close()


def test_agent_demo_manifest_validation_and_synthetic_airplane(tmp_path):
    import json
    from pathlib import Path

    from app.replay import import_file

    fixtures = Path(__file__).resolve().parents[1] / "fixtures"
    manifest_path = tmp_path / "agent.json"
    agent = {
        "scenario_id": "synthetic-motion",
        "synthetic": True,
        "cameras": {
            "camera_1": {"captured_start": "2026-01-01T12:00:00.000Z", "video": "camera_1.mp4"},
            "camera_2": {"captured_start": "2026-01-01T12:00:00.200Z", "video": "camera_2.mp4"},
        },
    }
    settings = Settings(database_path=tmp_path / "demo.sqlite3")
    store = Store(settings.db_path)
    try:
        manifest_path.write_text(json.dumps(agent))
        registered = import_file(
            store, fixtures / "agent-replay.json", agent_manifest=manifest_path
        )
        assert registered.scenario_id == "synthetic-motion"
        assert not store.has_snapshots(registered.scenario_id)
        agent["cameras"]["camera_2"]["captured_start"] = "2026-01-02T12:00:00Z"
        manifest_path.write_text(json.dumps(agent))
        with pytest.raises(ValueError, match="capture times"):
            import_file(store, fixtures / "agent-replay.json", agent_manifest=manifest_path)
        import_file(store, fixtures / "synthetic-replay.json")
        observation = Observation.model_validate_json(
            (fixtures / "synthetic-observation.json").read_bytes()
        )
        result = match(store, settings, observation)
        assert result.synthetic and result.status == "one"
        assert result.candidates[0].aircraft.callsign == "SYNTH01"
    finally:
        store.close()

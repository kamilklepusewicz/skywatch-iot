from math import asin, cos, radians, sin, sqrt

from .config import Settings
from .database import Store
from .models import Candidate, Coordinates, Match, Observation


def distance_km(a: Coordinates, b: Coordinates) -> float:
    lat_a, lat_b = radians(a.latitude), radians(b.latitude)
    delta_lon = radians(b.longitude - a.longitude)
    h = sin((lat_b - lat_a) / 2) ** 2 + cos(lat_a) * cos(lat_b) * sin(delta_lon / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(min(h, 1.0)))


def match(store: Store, settings: Settings, observation: Observation) -> Match:
    key = ""
    synthetic = False
    origin = settings.camera_locations.get(observation.camera_id)
    if observation.mode == "replay":
        scenario = store.scenario(observation.scenario_id) if observation.scenario_id else None
        if scenario is None:
            if observation.object_type != "airplane":
                return Match(status="skipped", reason="non_airplane")
            return Match(status="unavailable", reason="scenario_not_registered")
        key = scenario.scenario_id
        synthetic = scenario.synthetic
        origin = scenario.cameras.get(observation.camera_id)

    if observation.object_type != "airplane":
        return Match(status="skipped", reason="non_airplane", synthetic=synthetic)
    if origin is None:
        return Match(status="unavailable", reason="camera_location_missing", synthetic=synthetic)

    at = observation.captured_at.timestamp()
    window = settings.match_window_seconds
    max_age = settings.adsb_max_position_age_seconds
    snapshots = store.snapshots_between(key, at - window, at + window + max_age)
    if not snapshots:
        if store.has_snapshots(key):
            return Match(status="stale", reason="no_snapshot_near_frame", synthetic=synthetic)
        return Match(status="unavailable", reason="no_snapshots", synthetic=synthetic)

    candidates: dict[str, Candidate] = {}
    recent_snapshot = False
    recent_positions = False
    has_timed_positions = False
    incomplete = False
    for snapshot in snapshots:
        near = abs((snapshot.source_at - observation.captured_at).total_seconds()) <= window
        recent_snapshot |= near
        incomplete |= near and snapshot.missing_positions > 0
        for aircraft in snapshot.aircraft:
            if aircraft.on_ground is True:
                continue
            if aircraft.position_at is None or aircraft.position_age_seconds is None:
                incomplete |= near
                continue
            has_timed_positions = True
            delta = abs((aircraft.position_at - observation.captured_at).total_seconds())
            if delta > window or aircraft.position_age_seconds > max_age:
                continue
            recent_positions = True
            distance = distance_km(origin, aircraft)
            if distance > settings.match_radius_km:
                continue
            previous = candidates.get(aircraft.address)
            if previous is None or (delta, distance) < (
                previous.time_delta_seconds,
                previous.distance_km,
            ):
                candidates[aircraft.address] = Candidate(
                    aircraft=aircraft,
                    distance_km=distance,
                    time_delta_seconds=delta,
                    snapshot_at=snapshot.source_at,
                )

    ordered = sorted(
        candidates.values(),
        key=lambda c: (
            c.time_delta_seconds,
            c.distance_km,
            c.aircraft.address,
        ),
    )
    if ordered:
        return Match(
            status="one" if len(ordered) == 1 else "multiple",
            reason="temporal_geographic",
            candidate_count=len(ordered),
            candidates=ordered,
            synthetic=synthetic,
        )
    if incomplete and not recent_positions:
        return Match(status="unavailable", reason="positions_missing", synthetic=synthetic)
    if not recent_positions and (has_timed_positions or not recent_snapshot):
        return Match(status="stale", reason="no_position_near_frame", synthetic=synthetic)
    return Match(status="none", reason="no_aircraft_in_range", synthetic=synthetic)

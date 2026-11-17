import logging
import re
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from math import isfinite
from typing import Any

import httpx

from .models import Aircraft, Coordinates, Snapshot

LOG = logging.getLogger(__name__)
BASE_URL = "https://api.adsb.lol"
ADDRESS = re.compile(r"~?[0-9a-f]{6}", re.IGNORECASE)


def number(value: Any, low: float = -1e9, high: float = 1e9) -> float | None:
    if type(value) in (int, float) and low <= value <= high and isfinite(value):
        return float(value)
    return None


def text(value: Any) -> str | None:
    return (value.strip() or None) if isinstance(value, str) else None


def normalize(
    payload: Any,
    retrieved_at: datetime | None,
    *,
    scenario_id: str | None = None,
) -> Snapshot:
    if not isinstance(payload, dict) or not isinstance(payload.get("ac"), list):
        raise ValueError("ADS-B response must contain an ac array")
    epoch = number(payload.get("now"), 0, 253402300799000)
    if epoch is None:
        raise ValueError("ADS-B response must contain a valid now timestamp")
    # adsb.lol v2 uses milliseconds. Archives may store readsb's Unix seconds.
    source_at = datetime.fromtimestamp(epoch / 1000 if epoch >= 1e12 else epoch, UTC)
    aircraft: dict[str, Aircraft] = {}
    missing = 0
    for raw in payload["ac"]:
        if not isinstance(raw, dict):
            missing += 1
            continue
        address = text(raw.get("hex"))
        latitude = number(raw.get("lat"), -90, 90)
        longitude = number(raw.get("lon"), -180, 180)
        if (
            address is None
            or not ADDRESS.fullmatch(address)
            or latitude is None
            or longitude is None
        ):
            missing += 1
            continue
        address = address.lower()
        age = number(raw.get("seen_pos"), 0, 86400)
        baro = number(raw.get("alt_baro"))
        position = Aircraft(
            address=address,
            latitude=latitude,
            longitude=longitude,
            callsign=text(raw.get("flight")),
            aircraft_type=text(raw.get("t")),
            altitude_baro_ft=baro,
            altitude_geom_ft=number(raw.get("alt_geom")),
            on_ground=True
            if raw.get("alt_baro") == "ground"
            else False
            if baro is not None
            else None,
            ground_speed_kt=number(raw.get("gs"), 0),
            track_deg=number(raw.get("track"), 0, 360),
            position_age_seconds=age,
            position_at=source_at - timedelta(seconds=age) if age is not None else None,
        )
        old = aircraft.get(address)
        if old is None or (
            position.position_at is not None
            and (old.position_at is None or position.position_at > old.position_at)
        ):
            aircraft[address] = position
    return Snapshot(
        source_at=source_at,
        retrieved_at=retrieved_at,
        scenario_id=scenario_id,
        missing_positions=missing,
        aircraft=list(aircraft.values()),
    )


class PollError(Exception):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def retry_after(value: str | None, now: datetime) -> float | None:
    if not value:
        return None
    try:
        if value.isascii() and value.isdecimal():
            return float(int(value))
        date = parsedate_to_datetime(value)
        return max(0, (date - now).total_seconds()) if date.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


async def fetch_snapshot(
    client: httpx.AsyncClient,
    origin: Coordinates,
    radius_nm: int,
) -> Snapshot:
    try:
        response = await client.get(
            f"{BASE_URL}/v2/point/{origin.latitude}/{origin.longitude}/{radius_nm}",
        )
    except httpx.RequestError as exc:
        raise PollError(f"ADS-B network error ({type(exc).__name__})") from exc
    received = datetime.now(UTC)
    if response.status_code == 429:
        delay = retry_after(response.headers.get("Retry-After"), received)
        raise PollError("ADS-B rate limit reached (429)", 300 if delay is None else delay)
    if not response.is_success:
        raise PollError(f"ADS-B returned HTTP {response.status_code}")
    try:
        return normalize(response.json(), received)
    except (ValueError, OverflowError, RecursionError, OSError) as exc:
        raise PollError("ADS-B response has an invalid format") from exc

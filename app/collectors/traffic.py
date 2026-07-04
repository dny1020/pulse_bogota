"""Traffic collector backed by the TomTom Traffic Flow API (key-gated)."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.models import Place

log = get_logger(__name__)

_TOMTOM_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"


@dataclass
class TrafficReading:
    """One traffic observation: the 0-100 sub-score plus the raw speeds."""

    score: float
    current_speed_kmh: float | None = None
    free_flow_speed_kmh: float | None = None


def fetch_traffic(place: Place) -> TrafficReading | None:
    """Return the current traffic reading, or ``None`` if no key / unavailable.

    Congestion is derived from how far the current speed has dropped below the
    free-flow speed near the place. Higher score means busier. Raw speeds are
    kept alongside so scoring runs can persist them for future ML features.
    """
    settings = get_settings()
    if not settings.tomtom_api_key:
        return None

    params = {"point": f"{place.latitude},{place.longitude}", "key": settings.tomtom_api_key}
    try:
        resp = httpx.get(_TOMTOM_URL, params=params, timeout=settings.http_timeout_seconds)
        resp.raise_for_status()
        segment = resp.json()["flowSegmentData"]
        current = float(segment["currentSpeed"])
        free_flow = float(segment["freeFlowSpeed"])
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        log.warning("traffic_collector_failed", place_id=place.id, error=str(exc))
        return None

    if free_flow <= 0:
        return None
    congestion = max(0.0, 1.0 - current / free_flow)
    return TrafficReading(
        score=round(congestion * 100, 2),
        current_speed_kmh=current,
        free_flow_speed_kmh=free_flow,
    )


def fetch_traffic_score(place: Place) -> float | None:
    """Return only the 0-100 traffic sub-score (diagnostic endpoints)."""
    reading = fetch_traffic(place)
    return reading.score if reading else None

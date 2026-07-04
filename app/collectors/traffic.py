"""Traffic collector backed by the TomTom Traffic Flow API (key-gated)."""

from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.models import Place

log = get_logger(__name__)

_TOMTOM_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"


def fetch_traffic_score(place: Place) -> float | None:
    """Return a 0-100 congestion score, or ``None`` if no key / unavailable.

    Congestion is derived from how far the current speed has dropped below the
    free-flow speed near the place. Higher means busier.
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
    return round(congestion * 100, 2)

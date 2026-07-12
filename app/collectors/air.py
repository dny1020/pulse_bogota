"""Air quality collector backed by the free Open-Meteo API (no API key needed).

Air quality does not measure how busy a place is, so this signal never joins
the activity blend: it is informative (diagnostic endpoint) and stored raw in
History as a future ML feature.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.models import Place

log = get_logger(__name__)

_OPEN_METEO_AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"


@dataclass
class AirReading:
    """One air-quality observation: the 0-100 sub-score plus the raw values."""

    score: float
    pm2_5: float | None = None
    european_aqi: float | None = None


def fetch_air(place: Place) -> AirReading | None:
    """Return the current air-quality reading for a place, or ``None``.

    The score is a 0-100 'clean air' signal (higher means cleaner). Raw PM2.5
    and the European AQI are kept alongside so scoring runs can persist them.
    """
    settings = get_settings()
    params: dict[str, str | float] = {
        "latitude": place.latitude,
        "longitude": place.longitude,
        "current": "pm2_5,european_aqi",
    }
    try:
        resp = httpx.get(_OPEN_METEO_AIR_URL, params=params, timeout=settings.http_timeout_seconds)
        resp.raise_for_status()
        current = resp.json()["current"]
        aqi = current.get("european_aqi")
        pm2_5 = current.get("pm2_5")
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        log.warning("air_collector_failed", place_id=place.id, error=str(exc))
        return None

    if aqi is None:
        log.warning("air_collector_no_aqi", place_id=place.id)
        return None

    return AirReading(
        score=score_from_aqi(float(aqi)),
        pm2_5=float(pm2_5) if pm2_5 is not None else None,
        european_aqi=float(aqi),
    )


def fetch_air_score(place: Place) -> float | None:
    """Return only the 0-100 clean-air sub-score (diagnostic endpoints)."""
    reading = fetch_air(place)
    return reading.score if reading else None


def score_from_aqi(european_aqi: float) -> float:
    """Translate the European AQI into a 0-100 'clean air' score (pure).

    The EAQI grows with pollution (0 = pristine, 100+ = extremely poor), so the
    score is simply its inverse, clamped to the 0-100 range.
    """
    return round(100.0 - max(0.0, min(european_aqi, 100.0)), 2)

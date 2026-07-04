"""Weather collector backed by the free Open-Meteo API (no API key needed)."""

from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.models import Place

log = get_logger(__name__)

_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def fetch_weather_score(place: Place) -> float | None:
    """Return a 0-100 'pleasant weather' score, or ``None`` if unavailable.

    Higher means nicer weather, which tends to make places busier. Uses
    Open-Meteo current conditions; no API key required.
    """
    settings = get_settings()
    params: dict[str, str | float] = {
        "latitude": place.latitude,
        "longitude": place.longitude,
        "current": "temperature_2m,precipitation,cloud_cover",
    }
    try:
        resp = httpx.get(_OPEN_METEO_URL, params=params, timeout=settings.http_timeout_seconds)
        resp.raise_for_status()
        current = resp.json()["current"]
        return score_from_conditions(
            precipitation=float(current.get("precipitation", 0.0)),
            cloud_cover=float(current.get("cloud_cover", 0.0)),
        )
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        log.warning("weather_collector_failed", place_id=place.id, error=str(exc))
        return None


def score_from_conditions(precipitation: float, cloud_cover: float) -> float:
    """Translate raw conditions into a 0-100 'pleasant weather' score (pure).

    Rain dominates; heavy cloud cover adds a smaller penalty. >=5mm of rain is
    treated as fully unpleasant.
    """
    rain_penalty = min(precipitation / 5.0, 1.0) * 100
    cloud_penalty = min(max(cloud_cover, 0.0), 100.0)
    badness = 0.7 * rain_penalty + 0.3 * cloud_penalty
    return round(max(0.0, 100.0 - badness), 2)

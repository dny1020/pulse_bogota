"""Weather collector backed by the free Open-Meteo API (no API key needed)."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.models import Place

log = get_logger(__name__)

_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


@dataclass
class WeatherReading:
    """One weather observation: the 0-100 sub-score plus the raw values."""

    score: float
    temperature_c: float | None = None
    precipitation_mm: float | None = None


def fetch_weather(place: Place) -> WeatherReading | None:
    """Return the current weather reading for a place, or ``None``.

    The score is a 0-100 'pleasant weather' signal (higher means nicer, which
    tends to make places busier). Raw temperature and precipitation are kept
    alongside so scoring runs can persist them for future ML features.
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
        precipitation = float(current.get("precipitation", 0.0))
        cloud_cover = float(current.get("cloud_cover", 0.0))
        temperature = current.get("temperature_2m")
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        log.warning("weather_collector_failed", place_id=place.id, error=str(exc))
        return None

    return WeatherReading(
        score=score_from_conditions(precipitation=precipitation, cloud_cover=cloud_cover),
        temperature_c=float(temperature) if temperature is not None else None,
        precipitation_mm=precipitation,
    )


def fetch_weather_score(place: Place) -> float | None:
    """Return only the 0-100 weather sub-score (diagnostic endpoints)."""
    reading = fetch_weather(place)
    return reading.score if reading else None


def score_from_conditions(precipitation: float, cloud_cover: float) -> float:
    """Translate raw conditions into a 0-100 'pleasant weather' score (pure).

    Rain dominates; heavy cloud cover adds a smaller penalty. >=5mm of rain is
    treated as fully unpleasant.
    """
    rain_penalty = min(precipitation / 5.0, 1.0) * 100
    cloud_penalty = min(max(cloud_cover, 0.0), 100.0)
    badness = 0.7 * rain_penalty + 0.3 * cloud_penalty
    return round(max(0.0, 100.0 - badness), 2)

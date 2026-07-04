"""Events collector backed by the Eventbrite API (key-gated)."""

from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.models import Place

log = get_logger(__name__)

_EVENTBRITE_URL = "https://www.eventbriteapi.com/v3/events/search/"


def fetch_event_score(place: Place) -> float | None:
    """Return a 0-100 score from the count of nearby events, or ``None``.

    More events within a short radius means the area is likely busier. 20+
    nearby events saturate the score at 100.
    """
    settings = get_settings()
    if not settings.eventbrite_api_key:
        return None

    params: dict[str, str | float] = {
        "location.latitude": place.latitude,
        "location.longitude": place.longitude,
        "location.within": "2km",
    }
    headers = {"Authorization": f"Bearer {settings.eventbrite_api_key}"}
    try:
        resp = httpx.get(
            _EVENTBRITE_URL,
            params=params,
            headers=headers,
            timeout=settings.http_timeout_seconds,
        )
        resp.raise_for_status()
        count = int(resp.json().get("pagination", {}).get("object_count", 0))
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        log.warning("events_collector_failed", place_id=place.id, error=str(exc))
        return None

    return round(min(count / 20.0, 1.0) * 100, 2)

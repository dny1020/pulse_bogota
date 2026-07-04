"""Google Places collector: enriches place metadata (key-gated).

Unlike the other collectors this one does not produce an activity sub-score;
it refreshes ``rating``, ``rating_count`` and ``google_place_id`` which feed the
popularity signal and the discovery score.
"""

from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.models import Place

log = get_logger(__name__)

_FIND_PLACE_URL = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"


def fetch_place_metadata(place: Place) -> dict[str, object] | None:
    """Return ``{google_place_id, rating, rating_count}`` or ``None``.

    Returns ``None`` when no API key is configured or the lookup fails, so the
    caller can leave existing metadata untouched.
    """
    settings = get_settings()
    if not settings.google_places_api_key:
        return None

    params = {
        "input": f"{place.name} {place.city}",
        "inputtype": "textquery",
        "fields": "place_id,rating,user_ratings_total",
        "key": settings.google_places_api_key,
    }
    try:
        resp = httpx.get(_FIND_PLACE_URL, params=params, timeout=settings.http_timeout_seconds)
        resp.raise_for_status()
        candidates = resp.json().get("candidates", [])
        if not candidates:
            return None
        best = candidates[0]
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        log.warning("google_collector_failed", place_id=place.id, error=str(exc))
        return None

    return {
        "google_place_id": best.get("place_id"),
        "rating": best.get("rating"),
        "rating_count": best.get("user_ratings_total"),
    }

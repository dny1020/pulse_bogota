"""Events collector backed by the Ticketmaster Discovery API (key-gated).

Counts events starting near a place within the next ``events_window_hours``.
More nearby events means more people around, so the 0-100 score grows with
the count. Like every key-gated collector, a missing key or a failed request
returns ``None`` and the engine renormalises the remaining weights.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.models import Place

log = get_logger(__name__)

_TICKETMASTER_URL = "https://app.ticketmaster.com/discovery/v2/events.json"

# Events within the search window/radius that saturate the score at 100.
_SATURATION_EVENTS = 5


@dataclass
class EventsReading:
    """One events observation: the 0-100 sub-score plus the raw values."""

    score: float
    event_count: int | None = None
    next_event_starts_at: datetime | None = None


def fetch_events(place: Place) -> EventsReading | None:
    """Return the upcoming-events reading for a place, or ``None``.

    Args:
        place: The place whose surroundings are searched.

    Returns:
        An ``EventsReading`` with the 0-100 score, the event count and the
        start of the soonest event, or ``None`` when no key is configured or
        the request fails.
    """
    settings = get_settings()
    if not settings.ticketmaster_api_key:
        return None

    window_start = datetime.now(UTC)
    window_end = window_start + timedelta(hours=settings.events_window_hours)
    params: dict[str, str | int] = {
        "apikey": settings.ticketmaster_api_key,
        "latlong": f"{place.latitude},{place.longitude}",
        "radius": settings.events_radius_km,
        "unit": "km",
        "startDateTime": _format_datetime(window_start),
        "endDateTime": _format_datetime(window_end),
        "sort": "date,asc",
        "size": 1,
    }
    try:
        resp = httpx.get(_TICKETMASTER_URL, params=params, timeout=settings.http_timeout_seconds)
        resp.raise_for_status()
        payload = resp.json()
        count = int(payload["page"]["totalElements"])
        next_event_starts_at = _parse_next_event_start(payload)
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        log.warning("events_collector_failed", place_id=place.id, error=str(exc))
        return None

    return EventsReading(
        score=score_from_event_count(count),
        event_count=count,
        next_event_starts_at=next_event_starts_at,
    )


def fetch_event_score(place: Place) -> float | None:
    """Return only the 0-100 events sub-score (diagnostic endpoints)."""
    reading = fetch_events(place)
    return reading.score if reading else None


def score_from_event_count(count: int) -> float:
    """Translate an upcoming-event count into a 0-100 activity score (pure).

    Args:
        count: Number of events starting nearby within the search window.

    Returns:
        0 for no events, growing linearly and capped at 100 once the count
        reaches ``_SATURATION_EVENTS``.
    """
    ratio = min(max(count, 0) / _SATURATION_EVENTS, 1.0)
    return round(ratio * 100, 2)


def _format_datetime(moment: datetime) -> str:
    """Format a UTC datetime the way the Discovery API expects (no millis)."""
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_next_event_start(payload: dict) -> datetime | None:
    """Extract the start of the soonest event, or ``None`` if absent/TBA."""
    events = payload.get("_embedded", {}).get("events", [])
    if not events:
        return None
    raw_start = events[0].get("dates", {}).get("start", {}).get("dateTime")
    if not raw_start:
        return None
    return datetime.fromisoformat(raw_start.replace("Z", "+00:00"))

"""External data collectors: weather, traffic, events, air, Google and OSM.

Each collector has one responsibility and never calls another. The signal
collectors (weather/traffic/events/air) return a reading dataclass with a
0-100 sub-score plus the raw values; ``fetch_*_score`` wrappers expose just
the score for the diagnostic endpoints.

**Graceful degradation is the contract**: when an API key is missing or a
request fails the collector returns ``None`` and the engine renormalises the
remaining weights. Only Open-Meteo (weather, air) works with no key.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from app import __version__
from app.core import get_logger, get_settings
from app.database import Place

log = get_logger(__name__)


# --- weather (Open-Meteo, no key) -----------------------------------------

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


# --- air quality (Open-Meteo, no key) -------------------------------------

# Air quality does not measure how busy a place is, so this signal never joins
# the activity blend: it is informative (diagnostic endpoint) and stored raw in
# History as a future ML feature.
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


# --- traffic (TomTom, key-gated) ------------------------------------------

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


# --- events (Ticketmaster Discovery, key-gated) ---------------------------

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


# --- Google Places (key-gated, metadata only) -----------------------------

# Unlike the other collectors this one does not produce an activity sub-score;
# it refreshes rating/rating_count/google_place_id, which feed the popularity
# signal and the discovery score.
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


# --- OpenStreetMap / Overpass (no key, place discovery) -------------------

# Unlike the signal collectors this one does not produce a sub-score: it
# discovers discovery-friendly places (cafés, parks, viewpoints...) inside the
# configured bounding box so the importer service can store them.
_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_OVERPASS_TIMEOUT_SECONDS = 60.0
# Overpass rejects generic library User-Agents with 406; OSM policy asks for
# an identifying one with a contact point.
_USER_AGENT = f"pulse-bogota/{__version__} (github.com/dny1020/pulse_bogota)"

# OSM tag=value -> our place category (only discovery-friendly categories).
_TAG_CATEGORIES: dict[tuple[str, str], str] = {
    ("amenity", "cafe"): "cafe",
    ("amenity", "library"): "library",
    ("amenity", "marketplace"): "market",
    ("amenity", "arts_centre"): "cultural_center",
    ("tourism", "viewpoint"): "viewpoint",
    ("tourism", "museum"): "museum",
    ("leisure", "park"): "park",
    ("leisure", "garden"): "garden",
    ("shop", "books"): "bookstore",
}


@dataclass
class OsmPlace:
    """A named place candidate discovered on OpenStreetMap."""

    osm_id: str
    name: str
    category: str
    latitude: float
    longitude: float
    address: str | None = None


def fetch_osm_places(limit: int) -> list[OsmPlace]:
    """Query Overpass for named places in the configured bbox, capped at limit.

    Args:
        limit: Maximum number of candidates to return (spread across
            categories round-robin so cafés don't crowd out parks).

    Returns:
        Parsed place candidates; empty list when Overpass is unavailable.
    """
    settings = get_settings()
    query = _build_query(settings.osm_bbox)
    try:
        resp = httpx.post(
            _OVERPASS_URL,
            data={"data": query},
            timeout=_OVERPASS_TIMEOUT_SECONDS,
            headers={"User-Agent": _USER_AGENT},
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        log.warning("osm_importer_failed", error=str(exc))
        return []

    parsed = [place for element in elements if (place := _parse_element(element))]
    log.info("osm_places_fetched", found=len(parsed), limit=limit)
    return _round_robin_by_category(parsed, limit)


def _build_query(bbox: str) -> str:
    """Build the Overpass QL query for all mapped tags inside the bbox."""
    clauses = "\n".join(f'  nwr["{tag}"="{value}"]["name"];' for tag, value in _TAG_CATEGORIES)
    return f"[out:json][timeout:60][bbox:{bbox}];\n(\n{clauses}\n);\nout center;"


def _parse_element(element: dict) -> OsmPlace | None:
    """Turn one Overpass element into an OsmPlace, or ``None`` if unusable."""
    tags = element.get("tags", {})
    name = tags.get("name")
    if not name:
        return None

    category = next(
        (cat for (tag, value), cat in _TAG_CATEGORIES.items() if tags.get(tag) == value),
        None,
    )
    if category is None:
        return None

    # Nodes carry lat/lon directly; ways/relations carry a computed center.
    center = element.get("center", element)
    latitude, longitude = center.get("lat"), center.get("lon")
    if latitude is None or longitude is None:
        return None

    street = tags.get("addr:street")
    number = tags.get("addr:housenumber")
    address = f"{street} {number}".strip() if street else None

    return OsmPlace(
        osm_id=f"{element['type']}/{element['id']}",
        name=name.strip(),
        category=category,
        latitude=float(latitude),
        longitude=float(longitude),
        address=address,
    )


def _round_robin_by_category(places: list[OsmPlace], limit: int) -> list[OsmPlace]:
    """Cap the result at ``limit`` while keeping every category represented."""
    by_category: dict[str, list[OsmPlace]] = {}
    for place in places:
        by_category.setdefault(place.category, []).append(place)

    picked: list[OsmPlace] = []
    while len(picked) < limit and any(by_category.values()):
        for queue in by_category.values():
            if queue and len(picked) < limit:
                picked.append(queue.pop(0))
    return picked

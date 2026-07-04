"""OSM place importer backed by the free Overpass API (no key needed).

Unlike the signal collectors this module does not produce a sub-score: it
discovers discovery-friendly places (cafés, parks, viewpoints...) inside the
configured bounding box so the importer service can store them.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_OVERPASS_TIMEOUT_SECONDS = 60.0

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
        resp = httpx.post(_OVERPASS_URL, data={"data": query}, timeout=_OVERPASS_TIMEOUT_SECONDS)
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        log.warning("osm_importer_failed", error=str(exc))
        return []

    parsed = [place for element in elements if (place := _parse_element(element))]
    log.info("osm_places_fetched", found=len(parsed), limit=limit)
    return _round_robin_by_category(parsed, limit)

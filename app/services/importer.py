"""Imports OSM place candidates into the places table (idempotent upsert)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collectors import osm
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.database.models import Place
from app.services.scoring import score_place

log = get_logger(__name__)


def _upsert_candidate(
    db: Session, candidate: osm.OsmPlace, city: str, country: str
) -> Place | None:
    """Insert or refresh one candidate. Returns the new Place when created."""
    existing = db.scalar(select(Place).where(Place.osm_id == candidate.osm_id))
    if existing is None:
        # Adopt a manually created / seeded place with the same name instead
        # of duplicating it (e.g. the seed already has "Jardín Botánico").
        existing = db.scalar(
            select(Place).where(
                func.lower(Place.name) == candidate.name.lower(), Place.osm_id.is_(None)
            )
        )

    if existing is not None:
        existing.osm_id = candidate.osm_id
        existing.category = candidate.category
        existing.latitude = candidate.latitude
        existing.longitude = candidate.longitude
        if candidate.address:
            existing.address = candidate.address
        return None

    place = Place(
        osm_id=candidate.osm_id,
        name=candidate.name,
        category=candidate.category,
        latitude=candidate.latitude,
        longitude=candidate.longitude,
        address=candidate.address,
        city=city,
        country=country,
    )
    db.add(place)
    return place


def _effective_limit(db: Session, settings: Settings) -> int:
    """Grow the per-run import limit with the catalogue, capped at the max.

    Starts at ``osm_import_limit`` and rises as the table fills so the app keeps
    discovering new places over time, without ever asking Overpass for more than
    ``osm_import_limit_max`` candidates.
    """
    place_count = db.scalar(select(func.count()).select_from(Place)) or 0
    grown = int(place_count * settings.osm_import_growth)
    return min(settings.osm_import_limit_max, max(settings.osm_import_limit, grown))


def _score_new_places(db: Session, places: list[Place]) -> int:
    """Score freshly imported places so they have History immediately."""
    scored = 0
    for place in places:
        try:
            score_place(db, place)
            scored += 1
        except Exception as exc:  # a bad place must not abort the whole import
            log.error("osm_import_scoring_failed", place_id=place.id, error=str(exc))
    return scored


def import_osm_places(db: Session, *, limit: int | None = None) -> dict[str, int]:
    """Discover places on OSM and upsert them into the database.

    Idempotent: candidates are keyed on ``osm_id``, so re-running refreshes
    existing rows instead of duplicating them. Newly created places are scored
    right away so they have History without waiting for the next recalculation.

    Args:
        db: Database session.
        limit: Max candidates to import; defaults to a value that grows with the
            catalogue (see :func:`_effective_limit`).

    Returns:
        Counters: ``{"fetched": n, "created": n, "updated": n}``.
    """
    settings = get_settings()
    effective_limit = limit if limit is not None else _effective_limit(db, settings)
    candidates = osm.fetch_osm_places(limit=effective_limit)

    created_places: list[Place] = []
    for candidate in candidates:
        place = _upsert_candidate(db, candidate, settings.default_city, settings.default_country)
        if place is not None:
            created_places.append(place)
    db.commit()

    scored = _score_new_places(db, created_places)
    result = {
        "fetched": len(candidates),
        "created": len(created_places),
        "updated": len(candidates) - len(created_places),
    }
    log.info("osm_import_finished", **result, scored=scored)
    return result

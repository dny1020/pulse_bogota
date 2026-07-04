"""Imports OSM place candidates into the places table (idempotent upsert)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collectors import osm
from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.models import Place

log = get_logger(__name__)


def _upsert_candidate(db: Session, candidate: osm.OsmPlace, city: str, country: str) -> bool:
    """Insert or refresh one candidate. Returns True when a row was created."""
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
        return False

    db.add(
        Place(
            osm_id=candidate.osm_id,
            name=candidate.name,
            category=candidate.category,
            latitude=candidate.latitude,
            longitude=candidate.longitude,
            address=candidate.address,
            city=city,
            country=country,
        )
    )
    return True


def import_osm_places(db: Session, *, limit: int | None = None) -> dict[str, int]:
    """Discover places on OSM and upsert them into the database.

    Idempotent: candidates are keyed on ``osm_id``, so re-running refreshes
    existing rows instead of duplicating them. New places flow through the
    regular scoring path on the next recalculation.

    Args:
        db: Database session.
        limit: Max candidates to import; defaults to ``OSM_IMPORT_LIMIT``.

    Returns:
        Counters: ``{"fetched": n, "created": n, "updated": n}``.
    """
    settings = get_settings()
    candidates = osm.fetch_osm_places(limit=limit or settings.osm_import_limit)

    created = 0
    for candidate in candidates:
        if _upsert_candidate(db, candidate, settings.default_city, settings.default_country):
            created += 1
    db.commit()

    result = {"fetched": len(candidates), "created": created, "updated": len(candidates) - created}
    log.info("osm_import_finished", **result)
    return result

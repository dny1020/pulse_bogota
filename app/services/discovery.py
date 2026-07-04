"""Discovery engine: rank places by how interesting/under-explored they are.

Complements the activity score: a calm, well-rated, little-known café can rank
far above a famous-but-crowded landmark.
"""

from __future__ import annotations

import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.database.models import Place
from app.engine.score import compute_discovery
from app.schemas.discovery import DiscoveryRecommendation
from app.services.scoring import latest_history

log = get_logger(__name__)


def _log_request(kind: str, recs: list[DiscoveryRecommendation], **filters: object) -> None:
    """Log each recommendation request: raw material for a future ranking model."""
    log.info(
        "discover_request",
        kind=kind,
        results=len(recs),
        recommended_ids=[rec.id for rec in recs],
        **{name: value for name, value in filters.items() if value is not None},
    )


def _activity_for(db: Session, place: Place) -> int | None:
    record = latest_history(db, place.id)
    return record.activity_score if record else None


def _discovery_for(db: Session, place: Place) -> int:
    return compute_discovery(
        _activity_for(db, place), place.rating, place.rating_count, place.category
    )


def _recommend(db: Session, place: Place, reason: str) -> DiscoveryRecommendation:
    return DiscoveryRecommendation(
        id=place.id,
        name=place.name,
        category=place.category,
        activity_score=_activity_for(db, place),
        discovery_score=_discovery_for(db, place),
        reason=reason,
    )


def _filtered_places(
    db: Session,
    *,
    city: str | None,
    category: str | None,
    max_score: int | None,
) -> list[Place]:
    """Apply city/category filters in SQL and a max activity filter in Python."""
    stmt = select(Place)
    if city:
        stmt = stmt.where(Place.city == city)
    if category:
        stmt = stmt.where(Place.category == category)

    result: list[Place] = []
    for place in db.scalars(stmt):
        activity = _activity_for(db, place)
        if max_score is not None and activity is not None and activity > max_score:
            continue
        result.append(place)
    return result


def discover_quiet(
    db: Session, *, city: str | None = None, category: str | None = None, limit: int = 5
) -> list[DiscoveryRecommendation]:
    """The places with the lowest current activity (unknown activity last)."""
    places = _filtered_places(db, city=city, category=category, max_score=None)

    def _activity_key(place: Place) -> int:
        activity = _activity_for(db, place)
        return activity if activity is not None else 999

    places.sort(key=_activity_key)
    recs = [_recommend(db, p, "Among the quietest places right now") for p in places[:limit]]
    _log_request("quiet", recs, city=city, category=category, limit=limit)
    return recs


def discover_hidden(
    db: Session, *, city: str | None = None, category: str | None = None, limit: int = 5
) -> list[DiscoveryRecommendation]:
    """The highest discovery score: well-rated yet little explored."""
    places = _filtered_places(db, city=city, category=category, max_score=None)
    places.sort(key=lambda p: _discovery_for(db, p), reverse=True)
    recs = [_recommend(db, p, "Highly rated but little explored") for p in places[:limit]]
    _log_request("hidden", recs, city=city, category=category, limit=limit)
    return recs


def discover_random(
    db: Session,
    *,
    city: str | None = None,
    category: str | None = None,
    max_score: int | None = None,
    limit: int = 5,
    seed: int | None = None,
) -> list[DiscoveryRecommendation]:
    """A reproducible random pick of places matching the filters."""
    places = _filtered_places(db, city=city, category=category, max_score=max_score)
    random.Random(seed).shuffle(places)
    recs = [_recommend(db, p, "A spot that matches your filters") for p in places[:limit]]
    _log_request("random", recs, city=city, category=category, max_score=max_score, limit=limit)
    return recs


def discover_surprise(
    db: Session, *, city: str | None = None, limit: int = 5, seed: int | None = None
) -> list[DiscoveryRecommendation]:
    """One place per category, mixed together to break the routine."""
    by_category: dict[str, list[Place]] = {}
    for place in _filtered_places(db, city=city, category=None, max_score=None):
        by_category.setdefault(place.category, []).append(place)

    rng = random.Random(seed)
    categories = list(by_category)
    rng.shuffle(categories)
    chosen = [rng.choice(by_category[category]) for category in categories]
    recs = [_recommend(db, p, "Step out of your routine") for p in chosen[:limit]]
    _log_request("surprise", recs, city=city, limit=limit)
    return recs

"""Business logic for Place CRUD, search and geo queries."""

from __future__ import annotations

import math

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import Place
from app.schemas.place import PlaceCreate, PlaceUpdate


def list_places(db: Session) -> list[Place]:
    """Return all places ordered by name."""
    return list(db.scalars(select(Place).order_by(Place.name)))


def get_place(db: Session, place_id: int) -> Place | None:
    """Return a place by id, or ``None``."""
    return db.get(Place, place_id)


def create_place(db: Session, data: PlaceCreate) -> Place:
    """Persist a new place."""
    place = Place(**data.model_dump())
    db.add(place)
    db.commit()
    db.refresh(place)
    return place


def update_place(db: Session, place: Place, data: PlaceUpdate) -> Place:
    """Apply a partial update to an existing place."""
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(place, field, value)
    db.commit()
    db.refresh(place)
    return place


def delete_place(db: Session, place: Place) -> None:
    """Delete a place (and its history via cascade)."""
    db.delete(place)
    db.commit()


def search_places(db: Session, query: str) -> list[Place]:
    """Case-insensitive search over name and category."""
    pattern = f"%{query.lower()}%"
    stmt = (
        select(Place)
        .where(func.lower(Place.name).like(pattern) | func.lower(Place.category).like(pattern))
        .order_by(Place.name)
    )
    return list(db.scalars(stmt))


def nearby_places(db: Session, lat: float, lon: float, radius_km: float) -> list[Place]:
    """Return places within ``radius_km``, nearest first.

    Uses a cheap bounding-box prefilter in SQL, then an exact haversine
    distance in Python -- no PostGIS dependency required.
    """
    lat_delta = radius_km / 111.0
    lon_delta = radius_km / (111.0 * max(math.cos(math.radians(lat)), 0.01))
    stmt = select(Place).where(
        Place.latitude.between(lat - lat_delta, lat + lat_delta),
        Place.longitude.between(lon - lon_delta, lon + lon_delta),
    )
    with_distance = [
        (place, _haversine_km(lat, lon, place.latitude, place.longitude))
        for place in db.scalars(stmt)
    ]
    within = [(place, dist) for place, dist in with_distance if dist <= radius_km]
    within.sort(key=lambda item: item[1])
    return [place for place, _ in within]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points in kilometres."""
    earth_radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return 2 * earth_radius * math.asin(math.sqrt(a))

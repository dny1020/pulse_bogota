"""Seed the database with a curated set of real Bogotá places.

Ratings/counts are approximate and seeded so the API is useful before the
Google collector (if ever configured) refreshes them. Idempotent: only runs
when the places table is empty.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import Place

# name, category, lat, lon, address, rating, rating_count
_SEED: list[dict[str, object]] = [
    {
        "name": "Cerro de Monserrate",
        "category": "viewpoint",
        "latitude": 4.6058,
        "longitude": -74.0563,
        "address": "Cra. 2 Este No. 21-48 Paseo Bolívar",
        "rating": 4.7,
        "rating_count": 80000,
    },
    {
        "name": "Jardín Botánico José Celestino Mutis",
        "category": "garden",
        "latitude": 4.6686,
        "longitude": -74.0998,
        "address": "Av. Cl. 63 #68-95",
        "rating": 4.6,
        "rating_count": 30000,
    },
    {
        "name": "Parque Simón Bolívar",
        "category": "park",
        "latitude": 4.6580,
        "longitude": -74.0936,
        "address": "Cl. 53 #48-31",
        "rating": 4.6,
        "rating_count": 60000,
    },
    {
        "name": "Biblioteca Luis Ángel Arango",
        "category": "library",
        "latitude": 4.5965,
        "longitude": -74.0731,
        "address": "Cl. 11 #4-14",
        "rating": 4.7,
        "rating_count": 12000,
    },
    {
        "name": "Museo del Oro",
        "category": "museum",
        "latitude": 4.6019,
        "longitude": -74.0721,
        "address": "Cra. 6 #15-88",
        "rating": 4.7,
        "rating_count": 50000,
    },
    {
        "name": "Plaza de Bolívar",
        "category": "plaza",
        "latitude": 4.5980,
        "longitude": -74.0760,
        "address": "Cra. 7 #11-10",
        "rating": 4.6,
        "rating_count": 40000,
    },
    {
        "name": "Plaza de Usaquén",
        "category": "plaza",
        "latitude": 4.6953,
        "longitude": -74.0305,
        "address": "Cra. 6A #117-43",
        "rating": 4.5,
        "rating_count": 9000,
    },
    {
        "name": "Parque de la 93",
        "category": "park",
        "latitude": 4.6767,
        "longitude": -74.0483,
        "address": "Cl. 93A #12-32",
        "rating": 4.5,
        "rating_count": 15000,
    },
    {
        "name": "Parque El Virrey",
        "category": "park",
        "latitude": 4.6700,
        "longitude": -74.0540,
        "address": "Cl. 88 #15-40",
        "rating": 4.5,
        "rating_count": 8000,
    },
    {
        "name": "Café Devoción Zona G",
        "category": "cafe",
        "latitude": 4.6435,
        "longitude": -74.0626,
        "address": "Cl. 69 #4-65",
        "rating": 4.5,
        "rating_count": 3500,
    },
    {
        "name": "Librería Lerner Centro",
        "category": "bookstore",
        "latitude": 4.6010,
        "longitude": -74.0707,
        "address": "Av. Jiménez #4-35",
        "rating": 4.6,
        "rating_count": 1500,
    },
    {
        "name": "Quebrada La Vieja",
        "category": "trail",
        "latitude": 4.6450,
        "longitude": -74.0480,
        "address": "Cl. 71 con Cra. 1 Este",
        "rating": 4.6,
        "rating_count": 2500,
    },
    {
        "name": "Mercado de Paloquemao",
        "category": "market",
        "latitude": 4.6122,
        "longitude": -74.0876,
        "address": "Cra. 25 #19-48",
        "rating": 4.5,
        "rating_count": 20000,
    },
    {
        "name": "Centro Cultural Gabriel García Márquez",
        "category": "cultural_center",
        "latitude": 4.5972,
        "longitude": -74.0739,
        "address": "Cl. 11 #5-60",
        "rating": 4.6,
        "rating_count": 4000,
    },
]


def seed_places(db: Session) -> int:
    """Insert the seed places if the table is empty. Returns rows inserted."""
    existing = db.scalar(select(func.count()).select_from(Place))
    if existing:
        return 0
    db.add_all(Place(**data) for data in _SEED)
    db.commit()
    return len(_SEED)

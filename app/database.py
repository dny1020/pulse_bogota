"""Database: engine/session, ORM models, seed data and migrations.

Models are kept dialect-neutral so SQLite (dev + tests) and PostgreSQL
(Docker/prod) behave the same. The schema itself is owned by Alembic
(``app/migrations``), never by ``create_all()``; run it from the terminal with
``uv run python -m app.database``.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, create_engine, func, select
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from app.core import get_logger, get_settings

log = get_logger(__name__)

settings = get_settings()

# check_same_thread only matters for SQLite (used by the dev DB and tests).
_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
# pool_pre_ping revalidates pooled connections so the app survives a
# PostgreSQL restart without serving stale-connection errors.
engine = create_engine(settings.database_url, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Generator[Session]:
    """Yield a database session and ensure it is closed (FastAPI dependency)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _utcnow() -> datetime:
    return datetime.now(UTC)


# --- models ---------------------------------------------------------------


class Place(Base):
    """A place whose activity and discovery value we track."""

    __tablename__ = "places"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    address: Mapped[str | None] = mapped_column(String(300), default=None)
    city: Mapped[str] = mapped_column(String(120), default="Bogotá", index=True)
    country: Mapped[str] = mapped_column(String(120), default="Colombia")

    # Metadata enriched by the Google collector (when a key is configured).
    google_place_id: Mapped[str | None] = mapped_column(String(200), default=None)
    rating: Mapped[float | None] = mapped_column(Float, default=None)
    rating_count: Mapped[int | None] = mapped_column(Integer, default=None)

    # OSM element id ("node/123", "way/456") set by the Overpass importer.
    # Unique so re-imports update the same row instead of duplicating it.
    osm_id: Mapped[str | None] = mapped_column(String(60), default=None, unique=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    history: Mapped[list[History]] = relationship(
        back_populates="place", cascade="all, delete-orphan"
    )
    feedback: Mapped[list[Feedback]] = relationship(
        back_populates="place", cascade="all, delete-orphan"
    )


class History(Base):
    """Append-only record of one scoring run for a place."""

    __tablename__ = "history"

    id: Mapped[int] = mapped_column(primary_key=True)
    place_id: Mapped[int] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"), index=True)
    activity_score: Mapped[int] = mapped_column(Integer)

    # Component sub-scores (0-100). Nullable: a missing signal stays None.
    traffic_score: Mapped[float | None] = mapped_column(Float, default=None)
    weather_score: Mapped[float | None] = mapped_column(Float, default=None)
    event_score: Mapped[float | None] = mapped_column(Float, default=None)
    social_score: Mapped[float | None] = mapped_column(Float, default=None)

    # Raw signal values behind the sub-scores, kept for future ML features.
    temperature_c: Mapped[float | None] = mapped_column(Float, default=None)
    precipitation_mm: Mapped[float | None] = mapped_column(Float, default=None)
    current_speed_kmh: Mapped[float | None] = mapped_column(Float, default=None)
    free_flow_speed_kmh: Mapped[float | None] = mapped_column(Float, default=None)
    event_count: Mapped[int | None] = mapped_column(Integer, default=None)
    next_event_starts_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    place_rating: Mapped[float | None] = mapped_column(Float, default=None)
    place_rating_count: Mapped[int | None] = mapped_column(Integer, default=None)
    pm2_5: Mapped[float | None] = mapped_column(Float, default=None)
    european_aqi: Mapped[float | None] = mapped_column(Float, default=None)

    confidence: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )

    place: Mapped[Place] = relationship(back_populates="history")


class Feedback(Base):
    """Ground-truth crowd report from a visitor ("it was quiet/moderate/busy").

    These are the real labels the forecast model can learn from: a feedback
    close in time to a History row overrides that row's training target.
    """

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    place_id: Mapped[int] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"), index=True)
    # One of "quiet" / "moderate" / "busy" (validated at the API layer).
    level: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )

    place: Mapped[Place] = relationship(back_populates="feedback")


# --- seed -----------------------------------------------------------------

# Curated real Bogotá places. Ratings/counts are approximate and seeded so the
# API is useful before the Google collector (if ever configured) refreshes them.
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


# --- migrations -----------------------------------------------------------

# There is no alembic.ini: the script location is set here and the database URL
# comes from Settings inside the migration env, same as the app.
_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def run_migrations() -> None:
    """Upgrade the configured database to the latest schema revision.

    The database URL comes from Settings inside the migration env, so this
    works the same in Docker (PostgreSQL) and bare local runs (SQLite).
    """
    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    command.upgrade(config, "head")
    log.info("migrations_applied")


if __name__ == "__main__":
    run_migrations()

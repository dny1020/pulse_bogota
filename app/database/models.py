"""ORM models. Kept dialect-neutral so SQLite can be swapped for PostgreSQL."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


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

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

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    history: Mapped[list[History]] = relationship(
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

    confidence: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )

    place: Mapped[Place] = relationship(back_populates="history")

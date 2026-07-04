"""Pydantic schemas for the Place resource."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PlaceBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=80)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    address: str | None = None
    city: str = "Bogotá"
    country: str = "Colombia"
    google_place_id: str | None = None
    rating: float | None = Field(default=None, ge=0, le=5)
    rating_count: int | None = Field(default=None, ge=0)


class PlaceCreate(PlaceBase):
    """Payload to create a place."""


class PlaceUpdate(BaseModel):
    """Partial update: every field is optional."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    address: str | None = None
    city: str | None = None
    country: str | None = None
    google_place_id: str | None = None
    rating: float | None = Field(default=None, ge=0, le=5)
    rating_count: int | None = Field(default=None, ge=0)


class PlaceRead(PlaceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime

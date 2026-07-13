"""Pydantic request/response models for every endpoint."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# --- places ---------------------------------------------------------------


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


# --- activity & history ---------------------------------------------------


class ActivityRead(BaseModel):
    place_id: int
    name: str
    address: str | None
    latitude: float
    longitude: float
    score: int
    status: str
    confidence: float


class HistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    place_id: int
    activity_score: int
    traffic_score: float | None
    weather_score: float | None
    event_score: float | None
    social_score: float | None
    confidence: float
    created_at: datetime


# --- forecast -------------------------------------------------------------


class ForecastPoint(BaseModel):
    """Predicted activity for one future hour."""

    timestamp: datetime
    score: int
    status: str
    confidence: float
    model: str  # "baseline" or "gbm"


class ForecastResponse(BaseModel):
    place_id: int
    generated_at: datetime
    points: list[ForecastPoint]


class BestTimeResponse(BaseModel):
    """Best (quietest) and worst (busiest) predicted hour to visit a place."""

    place_id: int
    generated_at: datetime
    best: ForecastPoint
    worst: ForecastPoint


# --- discovery ------------------------------------------------------------


class DiscoveryRecommendation(BaseModel):
    id: int
    name: str
    category: str
    address: str | None
    coordinates: str  # "latitude,longitude" -- ready to paste into any maps app
    maps_url: str  # opens the place directly in Google Maps
    activity_score: int | None
    discovery_score: int
    confidence: float | None
    reason: str


class DiscoverResponse(BaseModel):
    recommendations: list[DiscoveryRecommendation]


# --- anomalies ------------------------------------------------------------


class AnomalyPoint(BaseModel):
    """A History reading that is unusually far from its place's typical level."""

    place_id: int
    timestamp: datetime
    activity_score: int
    z_score: float
    mean: float
    std: float
    # What the reading was compared against: its own (hour, weekday) cell when
    # that cell has enough samples, otherwise the place's global distribution.
    basis: Literal["hourly", "global"]


# --- feedback -------------------------------------------------------------

FeedbackLevel = Literal["quiet", "moderate", "busy"]


class FeedbackCreate(BaseModel):
    """A visitor's report of how crowded a place actually was."""

    level: FeedbackLevel


class FeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    place_id: int
    level: str
    created_at: datetime


# --- importer -------------------------------------------------------------


class OsmImportResult(BaseModel):
    fetched: int
    created: int
    updated: int

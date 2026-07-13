"""Pydantic schemas for the discovery endpoints."""

from __future__ import annotations

from pydantic import BaseModel


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

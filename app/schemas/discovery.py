"""Pydantic schemas for the discovery endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class DiscoveryRecommendation(BaseModel):
    id: int
    name: str
    category: str
    address: str | None
    latitude: float
    longitude: float
    activity_score: int | None
    discovery_score: int
    confidence: float | None
    reason: str


class DiscoverResponse(BaseModel):
    recommendations: list[DiscoveryRecommendation]

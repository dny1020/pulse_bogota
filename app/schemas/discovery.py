"""Pydantic schemas for the discovery endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class DiscoveryRecommendation(BaseModel):
    id: int
    name: str
    category: str
    activity_score: int | None
    discovery_score: int
    reason: str


class DiscoverResponse(BaseModel):
    recommendations: list[DiscoveryRecommendation]

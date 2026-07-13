"""Pydantic schema for the activity endpoint."""

from __future__ import annotations

from pydantic import BaseModel


class ActivityRead(BaseModel):
    place_id: int
    name: str
    address: str | None
    latitude: float
    longitude: float
    score: int
    status: str
    confidence: float

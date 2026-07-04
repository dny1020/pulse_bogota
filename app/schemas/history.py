"""Pydantic schema for History records."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


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

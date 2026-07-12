"""Pydantic schemas for the forecast endpoint."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


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

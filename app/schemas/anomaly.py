"""Pydantic schema for the anomaly-detection endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AnomalyPoint(BaseModel):
    """A History reading that is unusually far from its place's typical level."""

    place_id: int
    timestamp: datetime
    activity_score: int
    z_score: float
    mean: float
    std: float

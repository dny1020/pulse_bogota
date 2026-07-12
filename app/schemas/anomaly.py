"""Pydantic schema for the anomaly-detection endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


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

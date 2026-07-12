"""Pydantic schemas for visitor feedback (ground-truth crowd reports)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

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

"""Current activity score for a place."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.engine.score import status_label
from app.schemas.activity import ActivityRead
from app.services import places as places_service
from app.services import scoring as scoring_service

router = APIRouter(tags=["activity"])


@router.get("/activity/{place_id}", response_model=ActivityRead)
def get_activity(place_id: int, db: Session = Depends(get_db)) -> ActivityRead:
    if places_service.get_place(db, place_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Place not found")
    record = scoring_service.latest_history(db, place_id)
    if record is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No activity data yet; run POST /engine/recalculate",
        )
    return ActivityRead(
        place_id=place_id,
        score=record.activity_score,
        status=status_label(record.activity_score),
        confidence=record.confidence,
    )

"""Visitor feedback endpoints: real crowd labels for a place."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Feedback
from app.schemas.feedback import FeedbackCreate, FeedbackRead
from app.services import feedback as feedback_service
from app.services import places as places_service

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("/{place_id}", response_model=FeedbackRead, status_code=status.HTTP_201_CREATED)
def create_feedback(
    place_id: int, payload: FeedbackCreate, db: Session = Depends(get_db)
) -> Feedback:
    """Record how crowded a place actually was ("quiet"/"moderate"/"busy")."""
    if places_service.get_place(db, place_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Place not found")
    return feedback_service.create_feedback(db, place_id, payload.level)


@router.get("/{place_id}", response_model=list[FeedbackRead])
def list_feedback(place_id: int, db: Session = Depends(get_db)) -> list[Feedback]:
    """Return a place's feedback, newest first."""
    if places_service.get_place(db, place_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Place not found")
    return feedback_service.feedback_for_place(db, place_id)

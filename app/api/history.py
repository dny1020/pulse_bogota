"""History endpoint for a place."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import History
from app.schemas.history import HistoryRead
from app.services import places as places_service
from app.services import scoring as scoring_service

router = APIRouter(tags=["history"])


@router.get("/history/{place_id}", response_model=list[HistoryRead])
def get_history(place_id: int, db: Session = Depends(get_db)) -> list[History]:
    if places_service.get_place(db, place_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Place not found")
    return scoring_service.history_for_place(db, place_id)

"""Manual trigger to recalculate every place's activity score."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.services import scoring as scoring_service

router = APIRouter(prefix="/engine", tags=["engine"])


@router.post("/recalculate")
def recalculate(db: Session = Depends(get_db)) -> dict[str, int]:
    """Run all collectors for all places and persist fresh History rows."""
    count = scoring_service.recalculate_all(db)
    return {"recalculated_places": count}

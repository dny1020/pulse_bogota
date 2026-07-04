"""Top quiet / busy rankings by latest activity score."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.schemas.activity import ActivityRead
from app.services import scoring as scoring_service

router = APIRouter(prefix="/top", tags=["top"])


@router.get("/quiet", response_model=list[ActivityRead])
def top_quiet(
    limit: int = Query(5, ge=1, le=50), db: Session = Depends(get_db)
) -> list[ActivityRead]:
    return scoring_service.top_places(db, busiest=False, limit=limit)


@router.get("/busy", response_model=list[ActivityRead])
def top_busy(
    limit: int = Query(5, ge=1, le=50), db: Session = Depends(get_db)
) -> list[ActivityRead]:
    return scoring_service.top_places(db, busiest=True, limit=limit)

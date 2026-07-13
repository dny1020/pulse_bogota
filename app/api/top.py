"""Top busy ranking by latest activity score.

The quiet ranking lives at /discover/quiet instead: same sort order, but with
name/address/reason included, so this router does not duplicate it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.schemas.activity import ActivityRead
from app.services import scoring as scoring_service

router = APIRouter(prefix="/top", tags=["top"])


@router.get("/busy", response_model=list[ActivityRead])
def top_busy(
    limit: int = Query(5, ge=1, le=50), db: Session = Depends(get_db)
) -> list[ActivityRead]:
    return scoring_service.top_busy_places(db, limit=limit)

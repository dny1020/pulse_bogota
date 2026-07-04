"""Search and geo-proximity endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Place
from app.schemas.place import PlaceRead
from app.services import places as places_service

router = APIRouter(tags=["query"])


@router.get("/search", response_model=list[PlaceRead])
def search(
    q: str = Query(..., min_length=1, description="Text matched against name and category"),
    db: Session = Depends(get_db),
) -> list[Place]:
    return places_service.search_places(db, q)


@router.get("/nearby", response_model=list[PlaceRead])
def nearby(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius: float = Query(2.0, gt=0, le=50, description="Search radius in km"),
    db: Session = Depends(get_db),
) -> list[Place]:
    return places_service.nearby_places(db, lat, lon, radius)

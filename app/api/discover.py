"""Discovery endpoints: surface interesting, under-explored places."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.schemas.discovery import DiscoverResponse
from app.services import discovery as discovery_service

router = APIRouter(prefix="/discover", tags=["discover"])


@router.get("/quiet", response_model=DiscoverResponse)
def quiet(
    city: str | None = None,
    category: str | None = None,
    limit: int = Query(5, ge=1, le=50),
    db: Session = Depends(get_db),
) -> DiscoverResponse:
    recs = discovery_service.discover_quiet(db, city=city, category=category, limit=limit)
    return DiscoverResponse(recommendations=recs)


@router.get("/hidden", response_model=DiscoverResponse)
def hidden(
    city: str | None = None,
    category: str | None = None,
    limit: int = Query(5, ge=1, le=50),
    db: Session = Depends(get_db),
) -> DiscoverResponse:
    recs = discovery_service.discover_hidden(db, city=city, category=category, limit=limit)
    return DiscoverResponse(recommendations=recs)


@router.get("/random", response_model=DiscoverResponse)
def random_places(
    city: str | None = None,
    category: str | None = None,
    max_score: int | None = Query(None, ge=0, le=100),
    limit: int = Query(5, ge=1, le=50),
    seed: int | None = None,
    db: Session = Depends(get_db),
) -> DiscoverResponse:
    recs = discovery_service.discover_random(
        db, city=city, category=category, max_score=max_score, limit=limit, seed=seed
    )
    return DiscoverResponse(recommendations=recs)


@router.get("/surprise", response_model=DiscoverResponse)
def surprise(
    city: str | None = None,
    limit: int = Query(5, ge=1, le=50),
    seed: int | None = None,
    db: Session = Depends(get_db),
) -> DiscoverResponse:
    recs = discovery_service.discover_surprise(db, city=city, limit=limit, seed=seed)
    return DiscoverResponse(recommendations=recs)

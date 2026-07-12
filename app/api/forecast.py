"""Activity forecast for a place over the next hours."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.schemas.forecast import BestTimeResponse, ForecastResponse
from app.services import forecast as forecast_service
from app.services import places as places_service

router = APIRouter(tags=["forecast"])


@router.get("/forecast/{place_id}", response_model=ForecastResponse)
def get_forecast(
    place_id: int,
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
) -> ForecastResponse:
    """Predict the activity score for a place over the next ``hours`` hours."""
    place = places_service.get_place(db, place_id)
    if place is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Place not found")
    return forecast_service.forecast_place(db, place, hours)


@router.get("/forecast/{place_id}/best-time", response_model=BestTimeResponse)
def get_best_time(
    place_id: int,
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
) -> BestTimeResponse:
    """Return the quietest and busiest predicted hour within ``hours`` hours."""
    place = places_service.get_place(db, place_id)
    if place is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Place not found")
    return forecast_service.best_time(db, place, hours)

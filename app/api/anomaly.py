"""Detect unusual activity readings per place."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.schemas.anomaly import AnomalyPoint
from app.services import anomaly as anomaly_service
from app.services import places as places_service

router = APIRouter(tags=["anomalies"])


@router.get("/anomalies", response_model=list[AnomalyPoint])
def list_anomalies(db: Session = Depends(get_db)) -> list[AnomalyPoint]:
    """Return anomalous readings across every place."""
    return anomaly_service.detect_anomalies(db)


@router.get("/anomalies/{place_id}", response_model=list[AnomalyPoint])
def place_anomalies(place_id: int, db: Session = Depends(get_db)) -> list[AnomalyPoint]:
    """Return anomalous readings for one place."""
    if places_service.get_place(db, place_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Place not found")
    return anomaly_service.detect_anomalies(db, place_id=place_id)

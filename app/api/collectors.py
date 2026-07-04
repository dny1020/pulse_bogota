"""Run individual collectors on demand (diagnostics / manual refresh)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.services import scoring as scoring_service

router = APIRouter(prefix="/collector", tags=["collectors"])


@router.post("/weather")
def collect_weather(db: Session = Depends(get_db)) -> dict[str, object]:
    return {"collector": "weather", "results": scoring_service.run_signal_collector(db, "weather")}


@router.post("/traffic")
def collect_traffic(db: Session = Depends(get_db)) -> dict[str, object]:
    return {"collector": "traffic", "results": scoring_service.run_signal_collector(db, "traffic")}


@router.post("/events")
def collect_events(db: Session = Depends(get_db)) -> dict[str, object]:
    return {"collector": "events", "results": scoring_service.run_signal_collector(db, "events")}


@router.post("/google")
def collect_google(db: Session = Depends(get_db)) -> dict[str, object]:
    return {"collector": "google", "updated": scoring_service.run_google_enrichment(db)}

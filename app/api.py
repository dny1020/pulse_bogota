"""HTTP layer: every router, one per feature.

Routers stay thin — validation and serialisation here, logic in ``services.py``.
Every endpoint declares a ``response_model`` and gets its session via
``Depends(get_db)``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import __version__, services
from app.database import Feedback, History, Place, get_db
from app.schemas import (
    ActivityRead,
    AnomalyPoint,
    BestTimeResponse,
    DiscoverResponse,
    FeedbackCreate,
    FeedbackRead,
    ForecastResponse,
    HistoryRead,
    OsmImportResult,
    PlaceCreate,
    PlaceRead,
    PlaceUpdate,
)

health_router = APIRouter(tags=["health"])
places_router = APIRouter(prefix="/places", tags=["places"])
query_router = APIRouter(tags=["query"])
activity_router = APIRouter(tags=["activity"])
forecast_router = APIRouter(tags=["forecast"])
anomaly_router = APIRouter(tags=["anomalies"])
history_router = APIRouter(tags=["history"])
top_router = APIRouter(prefix="/top", tags=["top"])
engine_router = APIRouter(prefix="/engine", tags=["engine"])
collector_router = APIRouter(prefix="/collector", tags=["collectors"])
discover_router = APIRouter(prefix="/discover", tags=["discover"])
importer_router = APIRouter(prefix="/importer", tags=["importer"])
feedback_router = APIRouter(prefix="/feedback", tags=["feedback"])

ALL_ROUTERS = (
    health_router,
    places_router,
    query_router,
    activity_router,
    forecast_router,
    anomaly_router,
    history_router,
    top_router,
    engine_router,
    collector_router,
    discover_router,
    importer_router,
    feedback_router,
)


def _get_or_404(db: Session, place_id: int) -> Place:
    """Return the place or raise the 404 every place-scoped endpoint shares."""
    place = services.get_place(db, place_id)
    if place is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Place not found")
    return place


# --- health ---------------------------------------------------------------


@health_router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe: reports service status and the running API version."""
    return {"status": "ok", "version": __version__}


# --- places CRUD ----------------------------------------------------------


@places_router.get("", response_model=list[PlaceRead])
def list_places(db: Session = Depends(get_db)) -> list[Place]:
    return services.list_places(db)


@places_router.post("", response_model=PlaceRead, status_code=status.HTTP_201_CREATED)
def create_place(payload: PlaceCreate, db: Session = Depends(get_db)) -> Place:
    return services.create_place(db, payload)


@places_router.get("/{place_id}", response_model=PlaceRead)
def get_place(place_id: int, db: Session = Depends(get_db)) -> Place:
    return _get_or_404(db, place_id)


@places_router.put("/{place_id}", response_model=PlaceRead)
def update_place(place_id: int, payload: PlaceUpdate, db: Session = Depends(get_db)) -> Place:
    place = _get_or_404(db, place_id)
    return services.update_place(db, place, payload)


@places_router.delete("/{place_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_place(place_id: int, db: Session = Depends(get_db)) -> None:
    place = _get_or_404(db, place_id)
    services.delete_place(db, place)


# --- search & geo ---------------------------------------------------------


@query_router.get("/search", response_model=list[PlaceRead])
def search(
    q: str = Query(..., min_length=1, description="Text matched against name and category"),
    db: Session = Depends(get_db),
) -> list[Place]:
    return services.search_places(db, q)


@query_router.get("/nearby", response_model=list[PlaceRead])
def nearby(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius: float = Query(2.0, gt=0, le=50, description="Search radius in km"),
    db: Session = Depends(get_db),
) -> list[Place]:
    return services.nearby_places(db, lat, lon, radius)


# --- activity & top -------------------------------------------------------


@activity_router.get("/activity/{place_id}", response_model=ActivityRead)
def get_activity(place_id: int, db: Session = Depends(get_db)) -> ActivityRead:
    """Current activity score for a place."""
    place = _get_or_404(db, place_id)
    record = services.latest_history(db, place_id)
    if record is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No activity data yet; run POST /engine/recalculate",
        )
    return services.to_activity_read(place, record)


@top_router.get("/busy", response_model=list[ActivityRead])
def top_busy(
    limit: int = Query(5, ge=1, le=50), db: Session = Depends(get_db)
) -> list[ActivityRead]:
    """Busiest places right now. The quiet ranking lives at /discover/quiet:
    same sort order, but with name/address/reason included."""
    return services.top_busy_places(db, limit=limit)


# --- history --------------------------------------------------------------


@history_router.get("/history/{place_id}", response_model=list[HistoryRead])
def get_history(place_id: int, db: Session = Depends(get_db)) -> list[History]:
    _get_or_404(db, place_id)
    return services.history_for_place(db, place_id)


# --- forecast -------------------------------------------------------------


@forecast_router.get("/forecast/{place_id}", response_model=ForecastResponse)
def get_forecast(
    place_id: int,
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
) -> ForecastResponse:
    """Predict the activity score for a place over the next ``hours`` hours."""
    place = _get_or_404(db, place_id)
    return services.forecast_place(db, place, hours)


@forecast_router.get("/forecast/{place_id}/best-time", response_model=BestTimeResponse)
def get_best_time(
    place_id: int,
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
) -> BestTimeResponse:
    """Return the quietest and busiest predicted hour within ``hours`` hours."""
    place = _get_or_404(db, place_id)
    return services.best_time(db, place, hours)


# --- anomalies ------------------------------------------------------------


@anomaly_router.get("/anomalies", response_model=list[AnomalyPoint])
def list_anomalies(db: Session = Depends(get_db)) -> list[AnomalyPoint]:
    """Return anomalous readings across every place."""
    return services.detect_anomalies(db)


@anomaly_router.get("/anomalies/{place_id}", response_model=list[AnomalyPoint])
def place_anomalies(place_id: int, db: Session = Depends(get_db)) -> list[AnomalyPoint]:
    """Return anomalous readings for one place."""
    _get_or_404(db, place_id)
    return services.detect_anomalies(db, place_id=place_id)


# --- feedback -------------------------------------------------------------


@feedback_router.post(
    "/{place_id}", response_model=FeedbackRead, status_code=status.HTTP_201_CREATED
)
def create_feedback(
    place_id: int, payload: FeedbackCreate, db: Session = Depends(get_db)
) -> Feedback:
    """Record how crowded a place actually was ("quiet"/"moderate"/"busy")."""
    _get_or_404(db, place_id)
    return services.create_feedback(db, place_id, payload.level)


@feedback_router.get("/{place_id}", response_model=list[FeedbackRead])
def list_feedback(place_id: int, db: Session = Depends(get_db)) -> list[Feedback]:
    """Return a place's feedback, newest first."""
    _get_or_404(db, place_id)
    return services.feedback_for_place(db, place_id)


# --- discovery ------------------------------------------------------------


@discover_router.get("/quiet", response_model=DiscoverResponse)
def discover_quiet(
    city: str | None = None,
    category: str | None = None,
    limit: int = Query(5, ge=1, le=50),
    db: Session = Depends(get_db),
) -> DiscoverResponse:
    recs = services.discover_quiet(db, city=city, category=category, limit=limit)
    return DiscoverResponse(recommendations=recs)


@discover_router.get("/hidden", response_model=DiscoverResponse)
def discover_hidden(
    city: str | None = None,
    category: str | None = None,
    limit: int = Query(5, ge=1, le=50),
    db: Session = Depends(get_db),
) -> DiscoverResponse:
    recs = services.discover_hidden(db, city=city, category=category, limit=limit)
    return DiscoverResponse(recommendations=recs)


@discover_router.get("/random", response_model=DiscoverResponse)
def discover_random(
    city: str | None = None,
    category: str | None = None,
    max_score: int | None = Query(None, ge=0, le=100),
    limit: int = Query(5, ge=1, le=50),
    seed: int | None = None,
    db: Session = Depends(get_db),
) -> DiscoverResponse:
    recs = services.discover_random(
        db, city=city, category=category, max_score=max_score, limit=limit, seed=seed
    )
    return DiscoverResponse(recommendations=recs)


@discover_router.get("/surprise", response_model=DiscoverResponse)
def discover_surprise(
    city: str | None = None,
    limit: int = Query(5, ge=1, le=50),
    seed: int | None = None,
    db: Session = Depends(get_db),
) -> DiscoverResponse:
    recs = services.discover_surprise(db, city=city, limit=limit, seed=seed)
    return DiscoverResponse(recommendations=recs)


# --- engine & collectors (manual triggers / diagnostics) ------------------


@engine_router.post("/recalculate")
def recalculate(db: Session = Depends(get_db)) -> dict[str, int]:
    """Run all collectors for all places and persist fresh History rows."""
    count = services.recalculate_all(db)
    return {"recalculated_places": count}


@collector_router.post("/weather")
def collect_weather(db: Session = Depends(get_db)) -> dict[str, object]:
    return {"collector": "weather", "results": services.run_signal_collector(db, "weather")}


@collector_router.post("/traffic")
def collect_traffic(db: Session = Depends(get_db)) -> dict[str, object]:
    return {"collector": "traffic", "results": services.run_signal_collector(db, "traffic")}


@collector_router.post("/events")
def collect_events(db: Session = Depends(get_db)) -> dict[str, object]:
    return {"collector": "events", "results": services.run_signal_collector(db, "events")}


@collector_router.post("/air")
def collect_air(db: Session = Depends(get_db)) -> dict[str, object]:
    return {"collector": "air", "results": services.run_signal_collector(db, "air")}


@collector_router.post("/google")
def collect_google(db: Session = Depends(get_db)) -> dict[str, object]:
    return {"collector": "google", "updated": services.run_google_enrichment(db)}


# --- importer -------------------------------------------------------------


@importer_router.post("/osm", response_model=OsmImportResult)
def import_osm(
    limit: int | None = Query(None, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    """Discover places on OpenStreetMap (Overpass) and upsert them."""
    return services.import_osm_places(db, limit=limit)

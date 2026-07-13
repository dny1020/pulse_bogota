"""Business logic: places, scoring, discovery, forecasting, anomalies, imports.

Routers stay thin and call into here; the scheduler calls the same functions,
so there is a single code path for everything that touches the database.

Collectors and the pure engine are imported **as modules** (``collectors.fetch_weather``,
``engine.compute_activity``) rather than as loose functions: tests monkeypatch
those module attributes to stay offline, and a ``from ... import fetch_weather``
would bind the original and silently bypass the patch.
"""

from __future__ import annotations

import math
import os
import random
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

import joblib
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app import collectors, engine
from app.core import Settings, get_logger, get_settings
from app.database import Feedback, History, Place
from app.schemas import (
    ActivityRead,
    AnomalyPoint,
    BestTimeResponse,
    DiscoveryRecommendation,
    ForecastPoint,
    ForecastResponse,
    PlaceCreate,
    PlaceUpdate,
)

log = get_logger(__name__)

_BOGOTA_TZ = ZoneInfo("America/Bogota")


# --- places: CRUD, search and geo queries ---------------------------------


def list_places(db: Session) -> list[Place]:
    """Return all places ordered by name."""
    return list(db.scalars(select(Place).order_by(Place.name)))


def get_place(db: Session, place_id: int) -> Place | None:
    """Return a place by id, or ``None``."""
    return db.get(Place, place_id)


def create_place(db: Session, data: PlaceCreate) -> Place:
    """Persist a new place."""
    place = Place(**data.model_dump())
    db.add(place)
    db.commit()
    db.refresh(place)
    return place


def update_place(db: Session, place: Place, data: PlaceUpdate) -> Place:
    """Apply a partial update to an existing place."""
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(place, field, value)
    db.commit()
    db.refresh(place)
    return place


def delete_place(db: Session, place: Place) -> None:
    """Delete a place (and its history via cascade)."""
    db.delete(place)
    db.commit()


def search_places(db: Session, query: str) -> list[Place]:
    """Case-insensitive search over name and category."""
    pattern = f"%{query.lower()}%"
    stmt = (
        select(Place)
        .where(func.lower(Place.name).like(pattern) | func.lower(Place.category).like(pattern))
        .order_by(Place.name)
    )
    return list(db.scalars(stmt))


def nearby_places(db: Session, lat: float, lon: float, radius_km: float) -> list[Place]:
    """Return places within ``radius_km``, nearest first.

    Uses a cheap bounding-box prefilter in SQL, then an exact haversine
    distance in Python -- no PostGIS dependency required.
    """
    lat_delta = radius_km / 111.0
    lon_delta = radius_km / (111.0 * max(math.cos(math.radians(lat)), 0.01))
    stmt = select(Place).where(
        Place.latitude.between(lat - lat_delta, lat + lat_delta),
        Place.longitude.between(lon - lon_delta, lon + lon_delta),
    )
    with_distance = [
        (place, _haversine_km(lat, lon, place.latitude, place.longitude))
        for place in db.scalars(stmt)
    ]
    within = [(place, dist) for place, dist in with_distance if dist <= radius_km]
    within.sort(key=lambda item: item[1])
    return [place for place, _ in within]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points in kilometres."""
    earth_radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return 2 * earth_radius * math.asin(math.sqrt(a))


# --- scoring: the single path that runs collectors and writes History ------


def score_place(db: Session, place: Place) -> History:
    """Run every collector for one place, compute its score, persist History.

    Besides the 0-100 sub-scores, the raw signal values (temperature, rain,
    speeds, rating snapshot) are stored so future ML features have real data.
    """
    traffic_reading = collectors.fetch_traffic(place)
    weather_reading = collectors.fetch_weather(place)
    events_reading = collectors.fetch_events(place)
    # Informative only: air quality never joins the activity blend.
    air_reading = collectors.fetch_air(place)
    social_score = engine.popularity_score(place.rating, place.rating_count)

    activity, confidence = engine.compute_activity(
        {
            "traffic": traffic_reading.score if traffic_reading else None,
            "weather": weather_reading.score if weather_reading else None,
            "events": events_reading.score if events_reading else None,
            "popularity": social_score,
        }
    )
    record = History(
        place_id=place.id,
        activity_score=activity,
        traffic_score=traffic_reading.score if traffic_reading else None,
        weather_score=weather_reading.score if weather_reading else None,
        event_score=events_reading.score if events_reading else None,
        social_score=social_score,
        temperature_c=weather_reading.temperature_c if weather_reading else None,
        precipitation_mm=weather_reading.precipitation_mm if weather_reading else None,
        current_speed_kmh=traffic_reading.current_speed_kmh if traffic_reading else None,
        free_flow_speed_kmh=traffic_reading.free_flow_speed_kmh if traffic_reading else None,
        event_count=events_reading.event_count if events_reading else None,
        next_event_starts_at=events_reading.next_event_starts_at if events_reading else None,
        place_rating=place.rating,
        place_rating_count=place.rating_count,
        pm2_5=air_reading.pm2_5 if air_reading else None,
        european_aqi=air_reading.european_aqi if air_reading else None,
        confidence=confidence,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def recalculate_all(db: Session) -> int:
    """Score every place and return how many were processed."""
    places = list(db.scalars(select(Place)))
    for place in places:
        score_place(db, place)
    return len(places)


def latest_history(db: Session, place_id: int) -> History | None:
    """Return the most recent History row for a place, or ``None``."""
    stmt = (
        select(History)
        .where(History.place_id == place_id)
        .order_by(desc(History.created_at), desc(History.id))
        .limit(1)
    )
    return db.scalars(stmt).first()


def history_for_place(db: Session, place_id: int) -> list[History]:
    """Return a place's history, newest first."""
    stmt = (
        select(History)
        .where(History.place_id == place_id)
        .order_by(desc(History.created_at), desc(History.id))
    )
    return list(db.scalars(stmt))


def _activity_overview(db: Session) -> list[tuple[Place, History]]:
    """Pair each place with its latest history row (places that have one)."""
    overview: list[tuple[Place, History]] = []
    for place in db.scalars(select(Place)):
        record = latest_history(db, place.id)
        if record is not None:
            overview.append((place, record))
    return overview


def top_busy_places(db: Session, *, limit: int) -> list[ActivityRead]:
    """Return the busiest places by latest activity score, busiest first."""
    overview = _activity_overview(db)
    overview.sort(key=lambda pair: pair[1].activity_score, reverse=True)
    return [to_activity_read(place, record) for place, record in overview[:limit]]


def to_activity_read(place: Place, record: History) -> ActivityRead:
    """Pair a place with its latest reading for the activity/top endpoints."""
    return ActivityRead(
        place_id=place.id,
        name=place.name,
        address=place.address,
        latitude=place.latitude,
        longitude=place.longitude,
        score=record.activity_score,
        status=engine.status_label(record.activity_score),
        confidence=record.confidence,
    )


def run_signal_collector(db: Session, name: str) -> list[dict[str, object]]:
    """Run one signal collector for every place and report its raw values.

    Diagnostic only -- this does not persist History (use /engine/recalculate
    for that). Lets you confirm a collector / API key works independently.
    """
    collectors_by_name = {
        "weather": collectors.fetch_weather_score,
        "traffic": collectors.fetch_traffic_score,
        "events": collectors.fetch_event_score,
        "air": collectors.fetch_air_score,
    }
    collector = collectors_by_name[name]
    return [
        {"place_id": place.id, "name": place.name, "score": collector(place)}
        for place in db.scalars(select(Place))
    ]


def run_google_enrichment(db: Session) -> list[dict[str, object]]:
    """Refresh place metadata from Google Places and report what changed."""
    updated: list[dict[str, object]] = []
    for place in db.scalars(select(Place)):
        metadata = collectors.fetch_place_metadata(place)
        if not metadata:
            continue
        for field, value in metadata.items():
            if value is not None:
                setattr(place, field, value)
        updated.append({"place_id": place.id, "name": place.name, **metadata})
    db.commit()
    return updated


# --- discovery: rank places by how interesting/under-explored they are -----


def _log_request(kind: str, recs: list[DiscoveryRecommendation], **filters: object) -> None:
    """Log each recommendation request: raw material for a future ranking model."""
    log.info(
        "discover_request",
        kind=kind,
        results=len(recs),
        recommended_ids=[rec.id for rec in recs],
        **{name: value for name, value in filters.items() if value is not None},
    )


def _google_maps_url(latitude: float, longitude: float) -> str:
    """Google's cross-platform maps link: opens the app if installed, else web."""
    return f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"


def _recommend(db: Session, place: Place, reason: str) -> DiscoveryRecommendation:
    # One History lookup, reused for both activity_score and confidence
    # instead of the two separate queries _activity_for + a discovery lookup
    # would otherwise trigger.
    record = latest_history(db, place.id)
    activity_score = record.activity_score if record else None
    confidence = record.confidence if record else None
    discovery_score = engine.compute_discovery(
        activity_score, place.rating, place.rating_count, place.category
    )
    return DiscoveryRecommendation(
        id=place.id,
        name=place.name,
        category=place.category,
        address=place.address,
        coordinates=f"{place.latitude},{place.longitude}",
        maps_url=_google_maps_url(place.latitude, place.longitude),
        activity_score=activity_score,
        discovery_score=discovery_score,
        confidence=confidence,
        reason=reason,
    )


def _activity_for(db: Session, place: Place) -> int | None:
    record = latest_history(db, place.id)
    return record.activity_score if record else None


def _discovery_for(db: Session, place: Place) -> int:
    return engine.compute_discovery(
        _activity_for(db, place), place.rating, place.rating_count, place.category
    )


def _filtered_places(
    db: Session,
    *,
    city: str | None,
    category: str | None,
    max_score: int | None,
) -> list[Place]:
    """Apply city/category filters in SQL and a max activity filter in Python."""
    stmt = select(Place)
    if city:
        stmt = stmt.where(Place.city == city)
    if category:
        stmt = stmt.where(Place.category == category)

    result: list[Place] = []
    for place in db.scalars(stmt):
        activity = _activity_for(db, place)
        if max_score is not None and activity is not None and activity > max_score:
            continue
        result.append(place)
    return result


def discover_quiet(
    db: Session, *, city: str | None = None, category: str | None = None, limit: int = 5
) -> list[DiscoveryRecommendation]:
    """The places with the lowest current activity (unknown activity last)."""
    places = _filtered_places(db, city=city, category=category, max_score=None)

    def _activity_key(place: Place) -> int:
        activity = _activity_for(db, place)
        return activity if activity is not None else 999

    places.sort(key=_activity_key)
    recs = [_recommend(db, p, "Among the quietest places right now") for p in places[:limit]]
    _log_request("quiet", recs, city=city, category=category, limit=limit)
    return recs


def discover_hidden(
    db: Session, *, city: str | None = None, category: str | None = None, limit: int = 5
) -> list[DiscoveryRecommendation]:
    """The highest discovery score: well-rated yet little explored."""
    places = _filtered_places(db, city=city, category=category, max_score=None)
    places.sort(key=lambda p: _discovery_for(db, p), reverse=True)
    recs = [_recommend(db, p, "Highly rated but little explored") for p in places[:limit]]
    _log_request("hidden", recs, city=city, category=category, limit=limit)
    return recs


def discover_random(
    db: Session,
    *,
    city: str | None = None,
    category: str | None = None,
    max_score: int | None = None,
    limit: int = 5,
    seed: int | None = None,
) -> list[DiscoveryRecommendation]:
    """A reproducible random pick of places matching the filters."""
    places = _filtered_places(db, city=city, category=category, max_score=max_score)
    random.Random(seed).shuffle(places)
    recs = [_recommend(db, p, "A spot that matches your filters") for p in places[:limit]]
    _log_request("random", recs, city=city, category=category, max_score=max_score, limit=limit)
    return recs


def discover_surprise(
    db: Session, *, city: str | None = None, limit: int = 5, seed: int | None = None
) -> list[DiscoveryRecommendation]:
    """One place per category, mixed together to break the routine."""
    by_category: dict[str, list[Place]] = {}
    for place in _filtered_places(db, city=city, category=None, max_score=None):
        by_category.setdefault(place.category, []).append(place)

    rng = random.Random(seed)
    categories = list(by_category)
    rng.shuffle(categories)
    chosen = [rng.choice(by_category[category]) for category in categories]
    recs = [_recommend(db, p, "Step out of your routine") for p in chosen[:limit]]
    _log_request("surprise", recs, city=city, limit=limit)
    return recs


# --- forecasting: baseline profile now, trained model when data allows -----
#
# Every prediction falls back to the hourly-profile baseline when there is no
# trained model or a place lacks enough history, so an endpoint call never
# fails (same graceful-degradation contract as the collectors).


def forecast_place(db: Session, place: Place, hours: int) -> ForecastResponse:
    """Predict the activity score for ``place`` over the next ``hours`` hours.

    Args:
        db: Database session.
        place: The place to forecast (already validated to exist).
        hours: How many future hourly points to return.

    Returns:
        A :class:`ForecastResponse` with one point per future hour.
    """
    rows = history_for_place(db, place.id)  # newest first
    profile = engine.baseline_profile([(row.created_at, row.activity_score) for row in rows])
    place_average = sum(row.activity_score for row in rows) / len(rows) if rows else None
    recent_mean = place_average if place_average is not None else 50.0
    last_activity = float(rows[0].activity_score) if rows else 50.0
    # Future raw signals are unknown: assume the latest captured values persist.
    latest = rows[0] if rows else None

    settings = get_settings()
    model = _load_model() if len(rows) >= settings.forecast_min_samples else None

    now = datetime.now(_BOGOTA_TZ).replace(minute=0, second=0, microsecond=0)
    points: list[ForecastPoint] = []
    for step in range(1, hours + 1):
        target = now + timedelta(hours=step)
        if model is not None:
            score, confidence, used = _predict_with_model(
                model, target, place, recent_mean, last_activity, latest
            )
        else:
            score, confidence = engine.predict_baseline(profile, place_average, target)
            used = "baseline"
        points.append(
            ForecastPoint(
                timestamp=target,
                score=score,
                status=engine.status_label(score),
                confidence=confidence,
                model=used,
            )
        )
    return ForecastResponse(
        place_id=place.id,
        generated_at=datetime.now(_BOGOTA_TZ),
        points=points,
    )


def best_time(db: Session, place: Place, hours: int) -> BestTimeResponse:
    """Answer "what time should I go?" for the next ``hours`` hours.

    Reuses :func:`forecast_place` and picks the quietest predicted hour as
    ``best`` and the busiest as ``worst`` (earliest hour wins ties).

    Args:
        db: Database session.
        place: The place to evaluate (already validated to exist).
        hours: How many future hours to consider.

    Returns:
        A :class:`BestTimeResponse` with the best and worst hour to visit.
    """
    forecast = forecast_place(db, place, hours)
    best = min(forecast.points, key=lambda point: point.score)
    worst = max(forecast.points, key=lambda point: point.score)
    return BestTimeResponse(
        place_id=place.id,
        generated_at=forecast.generated_at,
        best=best,
        worst=worst,
    )


def _predict_with_model(
    bundle: dict[str, object],
    target: datetime,
    place: Place,
    recent_mean: float,
    last_activity: float,
    latest: History | None,
) -> tuple[int, float, str]:
    """Predict one point with the trained model; confidence derives from its MAE."""
    features = engine.build_feature_row(
        target=target,
        latitude=place.latitude,
        longitude=place.longitude,
        recent_mean=recent_mean,
        last_activity=last_activity,
        temperature_c=latest.temperature_c if latest else None,
        precipitation_mm=latest.precipitation_mm if latest else None,
        speed_ratio=engine.speed_ratio_from(
            latest.current_speed_kmh if latest else None,
            latest.free_flow_speed_kmh if latest else None,
        ),
        event_count=latest.event_count if latest else None,
    )
    estimator = bundle["model"]
    prediction = float(estimator.predict([features])[0])  # type: ignore[attr-defined]
    mae = float(bundle.get("mae", 25.0))  # type: ignore[arg-type]
    confidence = round(max(0.0, min(1.0, 1 - mae / 50)), 2)
    return round(max(0.0, min(100.0, prediction))), confidence, "gbm"


def _load_model() -> dict[str, object] | None:
    """Load the trained model bundle from disk, or ``None`` if unavailable.

    A bundle trained on a different feature layout is rejected (returns
    ``None`` → baseline applies) instead of crashing predictions with a shape
    mismatch; the next weekly training run replaces it.
    """
    path = get_settings().forecast_model_path
    if not os.path.exists(path):
        log.info("forecast_model_missing", path=path)
        return None
    try:
        bundle: dict[str, object] = joblib.load(path)
    except Exception as exc:  # pragma: no cover - defensive
        log.error("forecast_model_load_failed", path=path, error=str(exc))
        return None
    if bundle.get("feature_names") != engine.FEATURE_NAMES:
        log.warning("forecast_model_stale_features", path=path)
        return None
    return bundle


def train_model(db: Session) -> dict[str, object]:
    """Train the forecasting model from History and persist it if it helps.

    Builds a temporal train/test split, fits a ``HistGradientBoostingRegressor``
    and compares its MAE against the baseline. The model is only written to disk
    when it beats the baseline, so a bad model never replaces the simpler one.

    Returns:
        A summary dict (``trained``, ``rows``, and MAE figures when computed).
    """
    settings = get_settings()
    samples = _build_training_samples(db)
    if len(samples) < settings.forecast_min_samples:
        log.info("forecast_train_skipped", rows=len(samples), needed=settings.forecast_min_samples)
        return {"trained": False, "rows": len(samples), "reason": "insufficient_data"}

    samples.sort(key=lambda item: item[0])
    split = int(len(samples) * 0.8)
    train, test = samples[:split], samples[split:]
    if not test:
        return {"trained": False, "rows": len(samples), "reason": "no_test_split"}

    x_train = [features for _, features, _ in train]
    y_train = [target for _, _, target in train]
    x_test = [features for _, features, _ in test]
    y_test = [target for _, _, target in test]

    model = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, random_state=42)
    model.fit(x_train, y_train)
    model_mae = float(mean_absolute_error(y_test, model.predict(x_test)))

    # Baseline MAE on the same test set, using only the training rows.
    profile = engine.baseline_profile([(moment, target) for moment, _, target in train])
    train_avg = sum(y_train) / len(y_train)
    baseline_preds = [
        engine.predict_baseline(profile, train_avg, moment)[0] for moment, _, _ in test
    ]
    baseline_mae = float(mean_absolute_error(y_test, baseline_preds))

    result: dict[str, object] = {
        "rows": len(samples),
        "mae": round(model_mae, 2),
        "baseline_mae": round(baseline_mae, 2),
    }
    if model_mae < baseline_mae:
        _persist_model(model, model_mae, settings.forecast_model_path)
        result["trained"] = True
        log.info("forecast_model_trained", **result)
    else:
        result["trained"] = False
        result["reason"] = "no_improvement"
        log.info("forecast_train_no_improvement", **result)
    return result


def _build_training_samples(db: Session) -> list[tuple[datetime, list[float], int]]:
    """Turn History into ``(created_at, features, activity_score)`` samples.

    Lag features (``recent_mean``, ``last_activity``) are computed per place in
    chronological order so each sample only sees data available up to its time.
    When a visitor feedback exists close in time to a History row, its mapped
    score replaces the row's own estimate as the target — a real label beats
    the system's guess.
    """
    places = {place.id: place for place in db.scalars(select(Place))}
    by_place: dict[int, list[History]] = defaultdict(list)
    for row in db.scalars(select(History)):
        by_place[row.place_id].append(row)
    feedback_by_place = _feedback_targets(db)

    samples: list[tuple[datetime, list[float], int]] = []
    for place_id, rows in by_place.items():
        place = places.get(place_id)
        if place is None:
            continue
        rows.sort(key=lambda row: row.created_at)
        running_sum = 0.0
        previous: History | None = None
        for index, row in enumerate(rows):
            recent_mean = running_sum / index if index else float(row.activity_score)
            last_activity = (
                float(previous.activity_score) if previous else float(row.activity_score)
            )
            features = engine.build_feature_row(
                target=row.created_at,
                latitude=place.latitude,
                longitude=place.longitude,
                recent_mean=recent_mean,
                last_activity=last_activity,
                temperature_c=row.temperature_c,
                precipitation_mm=row.precipitation_mm,
                speed_ratio=engine.speed_ratio_from(row.current_speed_kmh, row.free_flow_speed_kmh),
                event_count=row.event_count,
            )
            target_score = _feedback_target_for(feedback_by_place.get(place_id, []), row.created_at)
            samples.append(
                (
                    row.created_at,
                    features,
                    target_score if target_score is not None else row.activity_score,
                )
            )
            running_sum += row.activity_score
            previous = row
    return samples


# A feedback counts as ground truth for History rows within this window.
_FEEDBACK_WINDOW = timedelta(minutes=90)


def _feedback_targets(db: Session) -> dict[int, list[tuple[datetime, int]]]:
    """Load all feedback as ``place_id -> [(created_at, mapped_score)]``."""
    targets: dict[int, list[tuple[datetime, int]]] = defaultdict(list)
    for row in db.scalars(select(Feedback)):
        score = LEVEL_TO_SCORE.get(row.level)
        if score is not None:
            targets[row.place_id].append((row.created_at, score))
    return targets


def _feedback_target_for(feedback: list[tuple[datetime, int]], moment: datetime) -> int | None:
    """Return the mapped score of the feedback closest to ``moment``, or ``None``.

    Only feedback within ``_FEEDBACK_WINDOW`` of the History row qualifies.
    """
    best: tuple[timedelta, int] | None = None
    for created_at, score in feedback:
        distance = abs(created_at - moment)
        if distance <= _FEEDBACK_WINDOW and (best is None or distance < best[0]):
            best = (distance, score)
    return best[1] if best else None


def _persist_model(model: HistGradientBoostingRegressor, mae: float, path: str) -> None:
    """Serialise the trained model, its MAE and the feature layout to ``path``."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    joblib.dump({"model": model, "mae": mae, "feature_names": engine.FEATURE_NAMES}, path)


# --- anomalies: model-free z-score per (hour, weekday) cell ----------------

# Need at least this many readings in a cell before its z-score means anything.
_MIN_READINGS = 3


def detect_anomalies(
    db: Session,
    *,
    place_id: int | None = None,
    threshold: float | None = None,
) -> list[AnomalyPoint]:
    """Return readings whose z-score crosses ``threshold``.

    Each reading is compared against its own ``(hour, weekday)`` cell (same
    bucketing as the forecast baseline) so "busy at 8pm" is judged against
    other 8pm readings, not the whole day. Cells with too few samples fall back
    to the place's global distribution, so sparse places still get detection.

    Args:
        db: Database session.
        place_id: Restrict to one place, or ``None`` to scan every place.
        threshold: Absolute z-score to flag; defaults to the configured value.

    Returns:
        Flagged readings, newest first within each place.
    """
    limit = threshold if threshold is not None else get_settings().anomaly_zscore_threshold
    place_ids = [place_id] if place_id is not None else [p.id for p in db.scalars(select(Place))]

    anomalies: list[AnomalyPoint] = []
    for pid in place_ids:
        rows = history_for_place(db, pid)  # newest first
        scores = [row.activity_score for row in rows]
        if len(scores) < _MIN_READINGS:
            continue
        global_mean = statistics.mean(scores)
        global_std = statistics.pstdev(scores)

        cells: dict[tuple[int, int], list[int]] = {}
        for row in rows:
            key = (row.created_at.hour, row.created_at.weekday())
            cells.setdefault(key, []).append(row.activity_score)

        for row in rows:
            cell_scores = cells[(row.created_at.hour, row.created_at.weekday())]
            basis: Literal["hourly", "global"]
            if len(cell_scores) >= _MIN_READINGS:
                mean = statistics.mean(cell_scores)
                std = statistics.pstdev(cell_scores)
                basis = "hourly"
            else:
                mean, std, basis = global_mean, global_std, "global"
            if std == 0:
                continue
            z_score = (row.activity_score - mean) / std
            if abs(z_score) >= limit:
                anomalies.append(
                    AnomalyPoint(
                        place_id=pid,
                        timestamp=row.created_at,
                        activity_score=row.activity_score,
                        z_score=round(z_score, 2),
                        mean=round(mean, 2),
                        std=round(std, 2),
                        basis=basis,
                    )
                )
    return anomalies


# --- feedback: the ground truth the forecast model learns from -------------

# A feedback level maps to the middle of its STATUS_BANDS range (engine.py);
# these become real training targets for the model.
LEVEL_TO_SCORE: dict[str, int] = {"quiet": 15, "moderate": 50, "busy": 85}


def create_feedback(db: Session, place_id: int, level: str) -> Feedback:
    """Persist one feedback report for a place.

    Args:
        db: Database session.
        place_id: The place the report is about (already validated to exist).
        level: One of ``"quiet"``, ``"moderate"``, ``"busy"``.

    Returns:
        The stored :class:`Feedback` row.
    """
    record = Feedback(place_id=place_id, level=level)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def feedback_for_place(db: Session, place_id: int) -> list[Feedback]:
    """Return a place's feedback, newest first."""
    stmt = (
        select(Feedback)
        .where(Feedback.place_id == place_id)
        .order_by(desc(Feedback.created_at), desc(Feedback.id))
    )
    return list(db.scalars(stmt))


# --- importer: discover OSM places and upsert them (idempotent) ------------


def import_osm_places(db: Session, *, limit: int | None = None) -> dict[str, int]:
    """Discover places on OSM and upsert them into the database.

    Idempotent: candidates are keyed on ``osm_id``, so re-running refreshes
    existing rows instead of duplicating them. Newly created places are scored
    right away so they have History without waiting for the next recalculation.

    Args:
        db: Database session.
        limit: Max candidates to import; defaults to a value that grows with the
            catalogue (see :func:`_effective_limit`).

    Returns:
        Counters: ``{"fetched": n, "created": n, "updated": n}``.
    """
    settings = get_settings()
    effective_limit = limit if limit is not None else _effective_limit(db, settings)
    candidates = collectors.fetch_osm_places(limit=effective_limit)

    created_places: list[Place] = []
    for candidate in candidates:
        place = _upsert_candidate(db, candidate, settings.default_city, settings.default_country)
        if place is not None:
            created_places.append(place)
    db.commit()

    scored = _score_new_places(db, created_places)
    result = {
        "fetched": len(candidates),
        "created": len(created_places),
        "updated": len(candidates) - len(created_places),
    }
    log.info("osm_import_finished", **result, scored=scored)
    return result


def _upsert_candidate(
    db: Session, candidate: collectors.OsmPlace, city: str, country: str
) -> Place | None:
    """Insert or refresh one candidate. Returns the new Place when created."""
    existing = db.scalar(select(Place).where(Place.osm_id == candidate.osm_id))
    if existing is None:
        # Adopt a manually created / seeded place with the same name instead
        # of duplicating it (e.g. the seed already has "Jardín Botánico").
        existing = db.scalar(
            select(Place).where(
                func.lower(Place.name) == candidate.name.lower(), Place.osm_id.is_(None)
            )
        )

    if existing is not None:
        existing.osm_id = candidate.osm_id
        existing.category = candidate.category
        existing.latitude = candidate.latitude
        existing.longitude = candidate.longitude
        if candidate.address:
            existing.address = candidate.address
        return None

    place = Place(
        osm_id=candidate.osm_id,
        name=candidate.name,
        category=candidate.category,
        latitude=candidate.latitude,
        longitude=candidate.longitude,
        address=candidate.address,
        city=city,
        country=country,
    )
    db.add(place)
    return place


def _effective_limit(db: Session, settings: Settings) -> int:
    """Grow the per-run import limit with the catalogue, capped at the max.

    Starts at ``osm_import_limit`` and rises as the table fills so the app keeps
    discovering new places over time, without ever asking Overpass for more than
    ``osm_import_limit_max`` candidates.
    """
    place_count = db.scalar(select(func.count()).select_from(Place)) or 0
    grown = int(place_count * settings.osm_import_growth)
    return min(settings.osm_import_limit_max, max(settings.osm_import_limit, grown))


def _score_new_places(db: Session, places: list[Place]) -> int:
    """Score freshly imported places so they have History immediately."""
    scored = 0
    for place in places:
        try:
            score_place(db, place)
            scored += 1
        except Exception as exc:  # a bad place must not abort the whole import
            log.error("osm_import_scoring_failed", place_id=place.id, error=str(exc))
    return scored

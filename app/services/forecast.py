"""Activity forecasting: baseline profile now, trained model when data allows.

Answers "what time should I go?" by predicting the activity score for the next
hours. It stays faithful to the project's graceful-degradation contract: every
prediction falls back to the hourly-profile baseline when there is no trained
model or a place lacks enough history, so an endpoint call never fails.
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import joblib
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.models import Feedback, History, Place
from app.engine import forecast as engine
from app.engine.score import status_label
from app.schemas.forecast import BestTimeResponse, ForecastPoint, ForecastResponse
from app.services.feedback import LEVEL_TO_SCORE
from app.services.scoring import history_for_place

log = get_logger(__name__)

_BOGOTA_TZ = ZoneInfo("America/Bogota")


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
                status=status_label(score),
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

"""Tests for activity forecasting: pure engine, service and endpoint."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import joblib
import pytest
from fastapi.testclient import TestClient
from sklearn.ensemble import HistGradientBoostingRegressor
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.models import History, Place
from app.engine import forecast as engine
from app.services import forecast as forecast_service
from app.services.forecast import train_model


def _make_place(db: Session) -> Place:
    place = Place(name="Café", category="cafe", latitude=4.6, longitude=-74.0)
    db.add(place)
    db.commit()
    db.refresh(place)
    return place


def _add_history(db: Session, place_id: int, points: list[tuple[datetime, int]]) -> None:
    for moment, score in points:
        db.add(History(place_id=place_id, activity_score=score, confidence=0.5, created_at=moment))
    db.commit()


# --- pure engine ----------------------------------------------------------


def test_baseline_profile_averages_same_cell() -> None:
    base = datetime(2026, 7, 6, 8, 0)
    rows = [(base, 40), (base + timedelta(days=7), 60)]  # same hour & weekday
    profile = engine.baseline_profile(rows)
    assert list(profile.values()) == [(50.0, 2)]


def test_predict_baseline_cell_then_average_then_neutral() -> None:
    base = datetime(2026, 7, 6, 8, 0)
    profile = engine.baseline_profile([(base, 40)])

    assert engine.predict_baseline(profile, 30.0, base) == (40, 0.25)
    # empty cell -> place average with a low fixed confidence
    assert engine.predict_baseline(profile, 30.0, base.replace(hour=9)) == (30, 0.2)
    # no history at all -> neutral 50, zero confidence
    assert engine.predict_baseline({}, None, base) == (50, 0.0)


def test_feature_row_flags_colombian_holiday() -> None:
    holiday = datetime(2026, 7, 20, 10, 0)  # Independence Day
    assert engine.is_colombian_holiday(holiday) is True
    row = engine.build_feature_row(
        target=holiday, latitude=4.6, longitude=-74.0, recent_mean=50.0, last_activity=40.0
    )
    assert len(row) == len(engine.FEATURE_NAMES)
    assert row[3] == 1.0  # is_holiday


def test_feature_row_imputes_missing_raw_signals() -> None:
    target = datetime(2026, 7, 6, 8, 0)
    row = engine.build_feature_row(
        target=target, latitude=4.6, longitude=-74.0, recent_mean=50.0, last_activity=40.0
    )
    # Missing raw signals get neutral values: Bogotá temp, dry, free flow, no events.
    assert row[-4:] == [15.0, 0.0, 1.0, 0.0]

    row = engine.build_feature_row(
        target=target,
        latitude=4.6,
        longitude=-74.0,
        recent_mean=50.0,
        last_activity=40.0,
        temperature_c=22.0,
        precipitation_mm=3.5,
        speed_ratio=0.4,
        event_count=2,
    )
    assert row[-4:] == [22.0, 3.5, 0.4, 2.0]


def test_speed_ratio_from_handles_missing_speeds() -> None:
    assert engine.speed_ratio_from(30.0, 60.0) == 0.5
    assert engine.speed_ratio_from(None, 60.0) is None
    assert engine.speed_ratio_from(30.0, None) is None
    assert engine.speed_ratio_from(30.0, 0.0) is None


# --- service --------------------------------------------------------------


def test_forecast_returns_hourly_points_from_baseline(db_session: Session) -> None:
    place = _make_place(db_session)
    base = datetime(2026, 6, 1, 8, tzinfo=UTC)
    _add_history(db_session, place.id, [(base + timedelta(hours=i), 40) for i in range(30)])

    response = forecast_service.forecast_place(db_session, place, hours=24)

    assert len(response.points) == 24
    assert all(point.model == "baseline" for point in response.points)
    assert all(0 <= point.score <= 100 for point in response.points)
    assert all(0.0 <= point.confidence <= 1.0 for point in response.points)


def test_forecast_without_history_is_neutral(db_session: Session) -> None:
    place = _make_place(db_session)
    response = forecast_service.forecast_place(db_session, place, hours=3)
    assert len(response.points) == 3
    assert all(point.score == 50 and point.confidence == 0.0 for point in response.points)


def test_train_model_skips_without_enough_data(db_session: Session) -> None:
    result = train_model(db_session)
    assert result["trained"] is False
    assert result["reason"] == "insufficient_data"


def test_train_model_runs_with_enough_data(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    monkeypatch.setenv("FORECAST_MIN_SAMPLES", "50")
    monkeypatch.setenv("FORECAST_MODEL_PATH", str(tmp_path / "model.joblib"))  # type: ignore[operator]
    get_settings.cache_clear()

    place = _make_place(db_session)
    base = datetime(2026, 1, 1, 0, tzinfo=UTC)
    _add_history(
        db_session, place.id, [(base + timedelta(hours=i), (i * 7) % 100) for i in range(120)]
    )

    result = train_model(db_session)
    assert result["rows"] == 120
    assert "trained" in result and "mae" in result


def _fit_dummy_model() -> HistGradientBoostingRegressor:
    model = HistGradientBoostingRegressor(max_iter=10)
    features = [
        [float(h), 0.0, 0.0, 0.0, 4.6, -74.0, 50.0, 50.0, 15.0, 0.0, 1.0, 0.0] for h in range(24)
    ] * 3
    targets = [h * 2 for h in range(24)] * 3
    model.fit(features, targets)
    return model


def test_forecast_uses_model_when_available(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    path = tmp_path / "model.joblib"  # type: ignore[operator]
    joblib.dump(
        {"model": _fit_dummy_model(), "mae": 5.0, "feature_names": engine.FEATURE_NAMES}, path
    )

    monkeypatch.setenv("FORECAST_MODEL_PATH", str(path))
    monkeypatch.setenv("FORECAST_MIN_SAMPLES", "5")
    get_settings.cache_clear()

    place = _make_place(db_session)
    base = datetime(2026, 6, 1, 8, tzinfo=UTC)
    _add_history(db_session, place.id, [(base + timedelta(hours=i), 40) for i in range(10)])

    response = forecast_service.forecast_place(db_session, place, hours=6)
    assert all(point.model == "gbm" for point in response.points)
    assert all(0 <= point.score <= 100 for point in response.points)


def test_stale_model_falls_back_to_baseline(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    """A bundle trained on an older feature layout must be ignored, not crash."""
    path = tmp_path / "model.joblib"  # type: ignore[operator]
    # Old-format bundle: no feature_names (pre-versioning) -> stale.
    joblib.dump({"model": _fit_dummy_model(), "mae": 5.0}, path)

    monkeypatch.setenv("FORECAST_MODEL_PATH", str(path))
    monkeypatch.setenv("FORECAST_MIN_SAMPLES", "5")
    get_settings.cache_clear()

    place = _make_place(db_session)
    base = datetime(2026, 6, 1, 8, tzinfo=UTC)
    _add_history(db_session, place.id, [(base + timedelta(hours=i), 40) for i in range(10)])

    response = forecast_service.forecast_place(db_session, place, hours=6)
    assert all(point.model == "baseline" for point in response.points)


# --- endpoint -------------------------------------------------------------


def test_forecast_endpoint(client: TestClient, db_session: Session) -> None:
    place = _make_place(db_session)
    response = client.get(f"/forecast/{place.id}", params={"hours": 6})
    assert response.status_code == 200
    body = response.json()
    assert body["place_id"] == place.id
    assert len(body["points"]) == 6


def test_forecast_endpoint_unknown_place(client: TestClient) -> None:
    assert client.get("/forecast/999").status_code == 404


def test_best_time_endpoint(client: TestClient, db_session: Session) -> None:
    place = _make_place(db_session)
    base = datetime(2026, 6, 1, 8, tzinfo=UTC)
    points = [(base + timedelta(hours=i), (i * 10) % 100) for i in range(48)]
    _add_history(db_session, place.id, points)

    response = client.get(f"/forecast/{place.id}/best-time", params={"hours": 24})
    assert response.status_code == 200
    body = response.json()
    assert body["place_id"] == place.id
    assert body["best"]["score"] <= body["worst"]["score"]


def test_best_time_endpoint_unknown_place(client: TestClient) -> None:
    assert client.get("/forecast/999/best-time").status_code == 404

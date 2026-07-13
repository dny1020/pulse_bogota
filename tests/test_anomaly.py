"""Tests for the z-score anomaly detection service and endpoint."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import History, Place
from app.services import detect_anomalies


def _make_place(db: Session) -> Place:
    place = Place(name="Parque", category="park", latitude=4.6, longitude=-74.0)
    db.add(place)
    db.commit()
    db.refresh(place)
    return place


def _add_history(db: Session, place_id: int, points: list[tuple[datetime, int]]) -> None:
    for moment, score in points:
        db.add(History(place_id=place_id, activity_score=score, confidence=0.5, created_at=moment))
    db.commit()


def test_detects_clear_outlier(db_session: Session) -> None:
    place = _make_place(db_session)
    base = datetime(2026, 6, 1, tzinfo=UTC)
    points = [(base + timedelta(hours=i), 50) for i in range(20)]
    points.append((base + timedelta(hours=21), 100))  # a busy day among quiet ones
    _add_history(db_session, place.id, points)

    anomalies = detect_anomalies(db_session, place_id=place.id)
    flagged = [anomaly for anomaly in anomalies if anomaly.activity_score == 100]
    assert flagged
    # Every (hour, weekday) cell has a single sample -> global fallback.
    assert all(anomaly.basis == "global" for anomaly in flagged)


def test_same_cell_outlier_uses_hourly_basis(db_session: Session) -> None:
    place = _make_place(db_session)
    monday_8am = datetime(2026, 6, 1, 8, tzinfo=UTC)  # a Monday
    points = [(monday_8am + timedelta(weeks=w), 50) for w in range(10)]
    points.append((monday_8am + timedelta(weeks=10), 100))  # unusual for Mondays 8am
    _add_history(db_session, place.id, points)

    anomalies = detect_anomalies(db_session, place_id=place.id)
    flagged = [anomaly for anomaly in anomalies if anomaly.activity_score == 100]
    assert flagged
    assert flagged[0].basis == "hourly"


def test_recurring_evening_peak_is_not_anomalous(db_session: Session) -> None:
    """A place that is always busy at one hour must not be flagged for it."""
    place = _make_place(db_session)
    monday_8am = datetime(2026, 6, 1, 8, tzinfo=UTC)
    monday_8pm = datetime(2026, 6, 1, 20, tzinfo=UTC)
    points = [(monday_8am + timedelta(weeks=w), 20) for w in range(30)]
    points += [(monday_8pm + timedelta(weeks=w), 90) for w in range(3)]  # normal peak
    _add_history(db_session, place.id, points)

    assert detect_anomalies(db_session, place_id=place.id) == []


def test_flat_series_has_no_anomaly(db_session: Session) -> None:
    place = _make_place(db_session)
    base = datetime(2026, 6, 1, tzinfo=UTC)
    _add_history(db_session, place.id, [(base + timedelta(hours=i), 50) for i in range(10)])

    assert detect_anomalies(db_session, place_id=place.id) == []


def test_anomalies_endpoint(client: TestClient, db_session: Session) -> None:
    place = _make_place(db_session)
    base = datetime(2026, 6, 1, tzinfo=UTC)
    points = [(base + timedelta(hours=i), 50) for i in range(20)]
    points.append((base + timedelta(hours=21), 100))
    _add_history(db_session, place.id, points)

    response = client.get(f"/anomalies/{place.id}")
    assert response.status_code == 200
    assert len(response.json()) >= 1


def test_anomalies_endpoint_unknown_place(client: TestClient) -> None:
    assert client.get("/anomalies/999").status_code == 404

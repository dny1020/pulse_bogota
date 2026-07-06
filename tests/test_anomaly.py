"""Tests for the z-score anomaly detection service and endpoint."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database.models import History, Place
from app.services.anomaly import detect_anomalies


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
    assert any(anomaly.activity_score == 100 for anomaly in anomalies)


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

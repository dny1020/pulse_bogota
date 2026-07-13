"""Tests for visitor feedback: endpoints and its use as training ground truth."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import Feedback, History, Place
from app.services import _build_training_samples


def _make_place(db: Session) -> Place:
    place = Place(name="Café", category="cafe", latitude=4.6, longitude=-74.0)
    db.add(place)
    db.commit()
    db.refresh(place)
    return place


def test_create_feedback(client: TestClient, db_session: Session) -> None:
    place = _make_place(db_session)
    response = client.post(f"/feedback/{place.id}", json={"level": "quiet"})
    assert response.status_code == 201
    body = response.json()
    assert body["place_id"] == place.id
    assert body["level"] == "quiet"


def test_create_feedback_rejects_invalid_level(client: TestClient, db_session: Session) -> None:
    place = _make_place(db_session)
    assert client.post(f"/feedback/{place.id}", json={"level": "packed"}).status_code == 422


def test_feedback_unknown_place(client: TestClient) -> None:
    assert client.post("/feedback/999", json={"level": "quiet"}).status_code == 404
    assert client.get("/feedback/999").status_code == 404


def test_list_feedback_newest_first(client: TestClient, db_session: Session) -> None:
    place = _make_place(db_session)
    client.post(f"/feedback/{place.id}", json={"level": "quiet"})
    client.post(f"/feedback/{place.id}", json={"level": "busy"})

    response = client.get(f"/feedback/{place.id}")
    assert response.status_code == 200
    levels = [item["level"] for item in response.json()]
    assert set(levels) == {"quiet", "busy"}


def test_feedback_overrides_training_target(db_session: Session) -> None:
    """A feedback close in time to a History row replaces its training target."""
    place = _make_place(db_session)
    moment = datetime(2026, 6, 1, 8, tzinfo=UTC)
    db_session.add(History(place_id=place.id, activity_score=70, confidence=0.5, created_at=moment))
    # "quiet" (-> 15) reported 30 minutes after the reading of 70.
    db_session.add(
        Feedback(place_id=place.id, level="quiet", created_at=moment + timedelta(minutes=30))
    )
    db_session.commit()

    samples = _build_training_samples(db_session)
    assert len(samples) == 1
    assert samples[0][2] == 15


def test_far_feedback_does_not_override_target(db_session: Session) -> None:
    place = _make_place(db_session)
    moment = datetime(2026, 6, 1, 8, tzinfo=UTC)
    db_session.add(History(place_id=place.id, activity_score=70, confidence=0.5, created_at=moment))
    # Reported a day later: outside the ±90-minute window.
    db_session.add(
        Feedback(place_id=place.id, level="quiet", created_at=moment + timedelta(days=1))
    )
    db_session.commit()

    samples = _build_training_samples(db_session)
    assert samples[0][2] == 70

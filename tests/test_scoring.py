"""Tests for the scoring flow: recalculate, activity, history, top."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import History


def test_recalculate_populates_activity(
    seeded_client: TestClient, offline_collectors: None
) -> None:
    recalculated = seeded_client.post("/engine/recalculate")
    assert recalculated.status_code == 200
    assert recalculated.json()["recalculated_places"] == 14

    place_id = seeded_client.get("/places").json()[0]["id"]
    activity = seeded_client.get(f"/activity/{place_id}")
    assert activity.status_code == 200
    body = activity.json()
    assert 0 <= body["score"] <= 100
    assert body["status"]
    # weather (0.25) + seeded popularity (0.15) available -> confidence 0.4.
    assert body["confidence"] == 0.4


def test_activity_404_before_recalculate(seeded_client: TestClient) -> None:
    place_id = seeded_client.get("/places").json()[0]["id"]
    assert seeded_client.get(f"/activity/{place_id}").status_code == 404


def test_history_recorded_per_run(seeded_client: TestClient, offline_collectors: None) -> None:
    place_id = seeded_client.get("/places").json()[0]["id"]
    seeded_client.post("/engine/recalculate")
    seeded_client.post("/engine/recalculate")
    history = seeded_client.get(f"/history/{place_id}")
    assert history.status_code == 200
    assert len(history.json()) == 2


def test_top_quiet_and_busy_ordering(seeded_client: TestClient, offline_collectors: None) -> None:
    seeded_client.post("/engine/recalculate")
    quiet = [item["score"] for item in seeded_client.get("/top/quiet").json()]
    busy = [item["score"] for item in seeded_client.get("/top/busy").json()]
    assert quiet == sorted(quiet)
    assert busy == sorted(busy, reverse=True)


def test_raw_signals_persisted_in_history(
    seeded_client: TestClient, db_session: Session, offline_collectors: None
) -> None:
    seeded_client.post("/engine/recalculate")
    record = db_session.scalars(select(History)).first()
    assert record is not None
    # Raw values from the (patched) weather reading.
    assert record.temperature_c == 18.0
    assert record.precipitation_mm == 0.0
    # Rating snapshot copied from the seeded place.
    assert record.place_rating is not None
    # Traffic disabled -> no raw speeds.
    assert record.current_speed_kmh is None
    assert record.free_flow_speed_kmh is None
    # Raw values from the (patched) air reading.
    assert record.pm2_5 == 12.5
    assert record.european_aqi == 30.0


def test_disabled_collectors_return_none(
    seeded_client: TestClient,
) -> None:
    # No API key configured -> traffic signal is None for every place.
    response = seeded_client.post("/collector/traffic")
    assert response.status_code == 200
    assert all(item["score"] is None for item in response.json()["results"])

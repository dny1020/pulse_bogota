"""Tests for the place CRUD, search and nearby endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import __version__


def test_health(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["version"] == __version__


def test_seed_is_listed(seeded_client: TestClient) -> None:
    response = seeded_client.get("/places")
    assert response.status_code == 200
    assert len(response.json()) == 14


def test_create_get_update_delete(client: TestClient) -> None:
    payload = {"name": "Test Cafe", "category": "cafe", "latitude": 4.6, "longitude": -74.07}
    created = client.post("/places", json=payload)
    assert created.status_code == 201
    place_id = created.json()["id"]

    assert client.get(f"/places/{place_id}").status_code == 200

    renamed = client.put(f"/places/{place_id}", json={"name": "Renamed Cafe"})
    assert renamed.json()["name"] == "Renamed Cafe"

    assert client.delete(f"/places/{place_id}").status_code == 204
    assert client.get(f"/places/{place_id}").status_code == 404


def test_get_missing_place_returns_404(client: TestClient) -> None:
    assert client.get("/places/999").status_code == 404


def test_create_rejects_invalid_coordinates(client: TestClient) -> None:
    bad = {"name": "X", "category": "cafe", "latitude": 200, "longitude": 0}
    assert client.post("/places", json=bad).status_code == 422


def test_search_matches_category(seeded_client: TestClient) -> None:
    response = seeded_client.get("/search", params={"q": "cafe"})
    assert response.status_code == 200
    names = [place["name"] for place in response.json()]
    assert any("Devoción" in name for name in names)


def test_nearby_returns_close_places(seeded_client: TestClient) -> None:
    response = seeded_client.get("/nearby", params={"lat": 4.598, "lon": -74.076, "radius": 2})
    assert response.status_code == 200
    assert len(response.json()) >= 1

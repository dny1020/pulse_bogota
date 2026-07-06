"""Tests for the OSM importer: parsing, capping and idempotent upsert."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collectors import osm
from app.collectors.osm import OsmPlace, _parse_element, _round_robin_by_category
from app.database.models import History, Place
from app.services.importer import import_osm_places


def _candidate(
    osm_id: str = "node/1", name: str = "Café Prueba", category: str = "cafe"
) -> OsmPlace:
    return OsmPlace(
        osm_id=osm_id,
        name=name,
        category=category,
        latitude=4.6,
        longitude=-74.07,
        address="Cra 1 #2-3",
    )


def test_parse_element_node_way_and_unnamed() -> None:
    node = {
        "type": "node",
        "id": 1,
        "lat": 4.6,
        "lon": -74.07,
        "tags": {"name": "X", "amenity": "cafe"},
    }
    way = {
        "type": "way",
        "id": 2,
        "center": {"lat": 4.61, "lon": -74.08},
        "tags": {"name": "P", "leisure": "park", "addr:street": "Cl 1", "addr:housenumber": "2"},
    }
    unnamed = {"type": "node", "id": 3, "lat": 4.6, "lon": -74.0, "tags": {"amenity": "cafe"}}

    parsed_node = _parse_element(node)
    assert parsed_node is not None
    assert parsed_node.osm_id == "node/1"
    assert parsed_node.category == "cafe"

    parsed_way = _parse_element(way)
    assert parsed_way is not None
    assert parsed_way.osm_id == "way/2"
    assert parsed_way.latitude == 4.61
    assert parsed_way.address == "Cl 1 2"

    assert _parse_element(unnamed) is None


def test_round_robin_keeps_every_category() -> None:
    cafes = [_candidate(osm_id=f"node/{i}") for i in range(5)]
    park = _candidate(osm_id="node/99", name="Parque Prueba", category="park")
    picked = _round_robin_by_category(cafes + [park], limit=3)
    assert len(picked) == 3
    assert any(place.category == "park" for place in picked)


def test_import_creates_then_updates(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, offline_collectors: None
) -> None:
    monkeypatch.setattr(osm, "fetch_osm_places", lambda limit: [_candidate()])

    first = import_osm_places(db_session)
    assert first == {"fetched": 1, "created": 1, "updated": 0}

    second = import_osm_places(db_session)
    assert second == {"fetched": 1, "created": 0, "updated": 1}

    total = db_session.scalar(select(func.count()).select_from(Place))
    assert total == 1


def test_import_scores_new_places(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, offline_collectors: None
) -> None:
    """A freshly imported place gets a History row immediately."""
    monkeypatch.setattr(osm, "fetch_osm_places", lambda limit: [_candidate()])

    import_osm_places(db_session)

    place = db_session.scalar(select(Place).where(Place.osm_id == "node/1"))
    assert place is not None
    history_count = db_session.scalar(
        select(func.count()).select_from(History).where(History.place_id == place.id)
    )
    assert history_count == 1


def test_import_adopts_existing_place_by_name(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_session.add(Place(name="Café Prueba", category="cafe", latitude=4.0, longitude=-74.0))
    db_session.commit()
    monkeypatch.setattr(osm, "fetch_osm_places", lambda limit: [_candidate()])

    result = import_osm_places(db_session)
    assert result == {"fetched": 1, "created": 0, "updated": 1}

    adopted = db_session.scalar(select(Place).where(Place.osm_id == "node/1"))
    assert adopted is not None
    assert adopted.name == "Café Prueba"


def test_import_endpoint(
    seeded_client: TestClient, monkeypatch: pytest.MonkeyPatch, offline_collectors: None
) -> None:
    monkeypatch.setattr(osm, "fetch_osm_places", lambda limit: [_candidate()])
    response = seeded_client.post("/importer/osm", params={"limit": 10})
    assert response.status_code == 200
    assert response.json() == {"fetched": 1, "created": 1, "updated": 0}

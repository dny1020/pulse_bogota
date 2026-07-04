"""Tests for the discovery endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_discover_quiet_is_sorted_by_activity(
    seeded_client: TestClient, offline_collectors: None
) -> None:
    seeded_client.post("/engine/recalculate")
    recs = seeded_client.get("/discover/quiet", params={"limit": 3}).json()["recommendations"]
    assert len(recs) == 3
    scores = [rec["activity_score"] for rec in recs]
    assert scores == sorted(scores)


def test_discover_random_is_reproducible_with_seed(
    seeded_client: TestClient, offline_collectors: None
) -> None:
    seeded_client.post("/engine/recalculate")
    first = seeded_client.get("/discover/random", params={"seed": 123, "limit": 5}).json()
    second = seeded_client.get("/discover/random", params={"seed": 123, "limit": 5}).json()
    assert first == second


def test_discover_hidden_ranks_by_discovery_score(
    seeded_client: TestClient, offline_collectors: None
) -> None:
    seeded_client.post("/engine/recalculate")
    recs = seeded_client.get("/discover/hidden", params={"limit": 5}).json()["recommendations"]
    scores = [rec["discovery_score"] for rec in recs]
    assert scores == sorted(scores, reverse=True)


def test_discover_surprise_mixes_categories(
    seeded_client: TestClient, offline_collectors: None
) -> None:
    seeded_client.post("/engine/recalculate")
    recs = seeded_client.get("/discover/surprise", params={"seed": 1}).json()["recommendations"]
    categories = [rec["category"] for rec in recs]
    assert len(categories) == len(set(categories))

"""Unit tests for the pure scoring engine."""

from __future__ import annotations

from app.engine.score import (
    compute_activity,
    compute_discovery,
    popularity_score,
    status_label,
)


def test_compute_activity_full_signals() -> None:
    score, confidence = compute_activity(
        {"traffic": 100, "weather": 100, "events": 100, "popularity": 100}
    )
    assert score == 100
    assert confidence == 1.0


def test_compute_activity_single_signal_keeps_value() -> None:
    score, confidence = compute_activity(
        {"traffic": None, "weather": 80, "events": None, "popularity": None}
    )
    assert score == 80
    assert confidence == 0.25


def test_compute_activity_renormalises_partial_signals() -> None:
    # weather(0.25)*100 + popularity(0.15)*20 over weight 0.40 -> 70.
    score, confidence = compute_activity({"weather": 100, "popularity": 20})
    assert score == 70
    assert confidence == 0.4


def test_compute_activity_no_signals() -> None:
    assert compute_activity({"traffic": None, "weather": None}) == (0, 0.0)


def test_status_label_boundaries() -> None:
    assert status_label(0) == "Very Quiet"
    assert status_label(20) == "Very Quiet"
    assert status_label(21) == "Quiet"
    assert status_label(60) == "Moderate"
    assert status_label(80) == "Busy"
    assert status_label(100) == "Very Busy"


def test_popularity_score_none_without_metadata() -> None:
    assert popularity_score(None, None) is None


def test_popularity_score_combines_rating_and_volume() -> None:
    assert popularity_score(5.0, 2000) == 100.0


def test_discovery_prefers_calm_well_rated_obscure_places() -> None:
    hidden = compute_discovery(activity_score=10, rating=4.8, rating_count=200, category="cafe")
    famous = compute_discovery(
        activity_score=90, rating=4.7, rating_count=80000, category="viewpoint"
    )
    assert hidden > famous

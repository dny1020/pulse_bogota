"""Tests for collector parsing and graceful degradation."""

from __future__ import annotations

import pytest

from app.collectors import events, google, traffic, weather
from app.collectors.weather import score_from_conditions
from app.database.models import Place


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def _place() -> Place:
    return Place(id=1, name="Test", category="park", latitude=4.6, longitude=-74.07)


def test_weather_score_from_conditions_is_pure() -> None:
    assert score_from_conditions(precipitation=0, cloud_cover=0) == 100.0
    assert score_from_conditions(precipitation=5, cloud_cover=100) == 0.0


def test_weather_fetch_parses_response(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"current": {"temperature_2m": 18, "precipitation": 0, "cloud_cover": 0}}
    monkeypatch.setattr(weather.httpx, "get", lambda *a, **k: _FakeResponse(payload))
    assert weather.fetch_weather_score(_place()) == 100.0


def test_weather_fetch_degrades_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise weather.httpx.HTTPError("network down")

    monkeypatch.setattr(weather.httpx, "get", boom)
    assert weather.fetch_weather_score(_place()) is None


def test_keyed_collectors_disabled_without_key() -> None:
    place = _place()
    assert traffic.fetch_traffic_score(place) is None
    assert events.fetch_event_score(place) is None
    assert google.fetch_place_metadata(place) is None

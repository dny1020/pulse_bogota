"""Tests for collector parsing and graceful degradation."""

from __future__ import annotations

import pytest

from app.collectors import air, events, google, traffic, weather
from app.collectors.air import score_from_aqi
from app.collectors.weather import score_from_conditions
from app.core.config import Settings
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


def test_weather_fetch_returns_raw_reading(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"current": {"temperature_2m": 18, "precipitation": 1.2, "cloud_cover": 50}}
    monkeypatch.setattr(weather.httpx, "get", lambda *a, **k: _FakeResponse(payload))
    reading = weather.fetch_weather(_place())
    assert reading is not None
    assert reading.temperature_c == 18.0
    assert reading.precipitation_mm == 1.2
    assert 0 <= reading.score <= 100


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


def test_air_score_from_aqi_is_pure() -> None:
    assert score_from_aqi(0.0) == 100.0
    assert score_from_aqi(40.0) == 60.0
    assert score_from_aqi(250.0) == 0.0  # clamped: extremely poor air


def test_air_fetch_parses_response(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"current": {"pm2_5": 12.5, "european_aqi": 30}}
    monkeypatch.setattr(air.httpx, "get", lambda *a, **k: _FakeResponse(payload))
    reading = air.fetch_air(_place())
    assert reading is not None
    assert reading.pm2_5 == 12.5
    assert reading.european_aqi == 30.0
    assert reading.score == 70.0


def test_air_fetch_degrades_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise air.httpx.HTTPError("network down")

    monkeypatch.setattr(air.httpx, "get", boom)
    assert air.fetch_air_score(_place()) is None


def test_air_fetch_degrades_without_aqi(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"current": {"pm2_5": None, "european_aqi": None}}
    monkeypatch.setattr(air.httpx, "get", lambda *a, **k: _FakeResponse(payload))
    assert air.fetch_air(_place()) is None


def test_event_score_from_count_is_pure() -> None:
    assert events.score_from_event_count(0) == 0.0
    assert events.score_from_event_count(1) == 20.0
    assert events.score_from_event_count(5) == 100.0
    assert events.score_from_event_count(50) == 100.0


def test_events_fetch_parses_response(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "page": {"totalElements": 2},
        "_embedded": {"events": [{"dates": {"start": {"dateTime": "2026-07-04T23:00:00Z"}}}]},
    }
    monkeypatch.setattr(events, "get_settings", _settings_with_ticketmaster_key)
    monkeypatch.setattr(events.httpx, "get", lambda *a, **k: _FakeResponse(payload))
    reading = events.fetch_events(_place())
    assert reading is not None
    assert reading.score == 40.0
    assert reading.event_count == 2
    assert reading.next_event_starts_at is not None
    assert reading.next_event_starts_at.isoformat() == "2026-07-04T23:00:00+00:00"


def test_events_fetch_handles_zero_events(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"page": {"totalElements": 0}}
    monkeypatch.setattr(events, "get_settings", _settings_with_ticketmaster_key)
    monkeypatch.setattr(events.httpx, "get", lambda *a, **k: _FakeResponse(payload))
    reading = events.fetch_events(_place())
    assert reading is not None
    assert reading.score == 0.0
    assert reading.event_count == 0
    assert reading.next_event_starts_at is None


def test_events_fetch_degrades_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise events.httpx.HTTPError("network down")

    monkeypatch.setattr(events, "get_settings", _settings_with_ticketmaster_key)
    monkeypatch.setattr(events.httpx, "get", boom)
    assert events.fetch_event_score(_place()) is None


def _settings_with_ticketmaster_key() -> Settings:
    return Settings(ticketmaster_api_key="test-key")

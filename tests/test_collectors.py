"""Tests for collector parsing and graceful degradation."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app import collectors
from app.collectors import score_from_aqi, score_from_conditions
from app.core import Settings, get_settings
from app.database import Place


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
    monkeypatch.setattr(collectors.httpx, "get", lambda *a, **k: _FakeResponse(payload))
    assert collectors.fetch_weather_score(_place()) == 100.0


def test_weather_fetch_returns_raw_reading(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"current": {"temperature_2m": 18, "precipitation": 1.2, "cloud_cover": 50}}
    monkeypatch.setattr(collectors.httpx, "get", lambda *a, **k: _FakeResponse(payload))
    reading = collectors.fetch_weather(_place())
    assert reading is not None
    assert reading.temperature_c == 18.0
    assert reading.precipitation_mm == 1.2
    assert 0 <= reading.score <= 100


def test_weather_fetch_degrades_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise collectors.httpx.HTTPError("network down")

    monkeypatch.setattr(collectors.httpx, "get", boom)
    assert collectors.fetch_weather_score(_place()) is None


def test_keyed_collectors_disabled_without_key() -> None:
    place = _place()
    assert collectors.fetch_traffic_score(place) is None
    assert collectors.fetch_event_score(place) is None
    assert collectors.fetch_place_metadata(place) is None


@pytest.fixture
def tomtom_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Enable the traffic collector with a recognisable fake key."""
    key = "tomtom-secret-key"
    monkeypatch.setenv("TOMTOM_API_KEY", key)
    get_settings.cache_clear()
    yield key
    get_settings.cache_clear()


def _traffic_response(*args: object, **kwargs: object) -> _FakeResponse:
    return _FakeResponse({"flowSegmentData": {"currentSpeed": 20, "freeFlowSpeed": 40}})


def test_traffic_reading_is_cached_between_calls(
    monkeypatch: pytest.MonkeyPatch, tomtom_key: str
) -> None:
    calls = 0

    def counting_get(*args: object, **kwargs: object) -> _FakeResponse:
        nonlocal calls
        calls += 1
        return _traffic_response()

    monkeypatch.setattr(collectors.httpx, "get", counting_get)
    first = collectors.fetch_traffic(_place())
    second = collectors.fetch_traffic(_place())

    assert calls == 1
    assert first is not None and second is not None
    assert first.score == second.score == 50.0


def test_traffic_refetches_once_the_cache_expires(
    monkeypatch: pytest.MonkeyPatch, tomtom_key: str
) -> None:
    calls = 0

    def counting_get(*args: object, **kwargs: object) -> _FakeResponse:
        nonlocal calls
        calls += 1
        return _traffic_response()

    monkeypatch.setattr(collectors.httpx, "get", counting_get)
    monkeypatch.setenv("TRAFFIC_CACHE_MINUTES", "0")
    get_settings.cache_clear()

    collectors.fetch_traffic(_place())
    collectors.fetch_traffic(_place())
    assert calls == 2


def test_traffic_stops_calling_once_the_daily_budget_is_spent(
    monkeypatch: pytest.MonkeyPatch, tomtom_key: str
) -> None:
    monkeypatch.setattr(collectors.httpx, "get", _traffic_response)
    monkeypatch.setenv("TRAFFIC_CACHE_MINUTES", "0")
    monkeypatch.setenv("TOMTOM_DAILY_BUDGET", "2")
    get_settings.cache_clear()

    place = _place()
    assert collectors.fetch_traffic(place) is not None
    assert collectors.fetch_traffic(place) is not None
    # Budget spent: the signal drops out instead of burning quota on a 403.
    assert collectors.fetch_traffic(place) is None


def test_traffic_error_does_not_log_the_api_key(
    monkeypatch: pytest.MonkeyPatch, tomtom_key: str, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise collectors.httpx.HTTPError(
            f"Client error '403 Forbidden' for url 'https://api.tomtom.com/x?key={tomtom_key}'"
        )

    monkeypatch.setattr(collectors.httpx, "get", boom)
    assert collectors.fetch_traffic(_place()) is None

    logged = capsys.readouterr().out
    assert "traffic_collector_failed" in logged
    assert tomtom_key not in logged
    assert "key=***" in logged


def test_air_score_from_aqi_is_pure() -> None:
    assert score_from_aqi(0.0) == 100.0
    assert score_from_aqi(40.0) == 60.0
    assert score_from_aqi(250.0) == 0.0  # clamped: extremely poor air


def test_air_fetch_parses_response(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"current": {"pm2_5": 12.5, "european_aqi": 30}}
    monkeypatch.setattr(collectors.httpx, "get", lambda *a, **k: _FakeResponse(payload))
    reading = collectors.fetch_air(_place())
    assert reading is not None
    assert reading.pm2_5 == 12.5
    assert reading.european_aqi == 30.0
    assert reading.score == 70.0


def test_air_fetch_degrades_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise collectors.httpx.HTTPError("network down")

    monkeypatch.setattr(collectors.httpx, "get", boom)
    assert collectors.fetch_air_score(_place()) is None


def test_air_fetch_degrades_without_aqi(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"current": {"pm2_5": None, "european_aqi": None}}
    monkeypatch.setattr(collectors.httpx, "get", lambda *a, **k: _FakeResponse(payload))
    assert collectors.fetch_air(_place()) is None


def test_event_score_from_count_is_pure() -> None:
    assert collectors.score_from_event_count(0) == 0.0
    assert collectors.score_from_event_count(1) == 20.0
    assert collectors.score_from_event_count(5) == 100.0
    assert collectors.score_from_event_count(50) == 100.0


def test_events_fetch_parses_response(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "page": {"totalElements": 2},
        "_embedded": {"events": [{"dates": {"start": {"dateTime": "2026-07-04T23:00:00Z"}}}]},
    }
    monkeypatch.setattr(collectors, "get_settings", _settings_with_ticketmaster_key)
    monkeypatch.setattr(collectors.httpx, "get", lambda *a, **k: _FakeResponse(payload))
    reading = collectors.fetch_events(_place())
    assert reading is not None
    assert reading.score == 40.0
    assert reading.event_count == 2
    assert reading.next_event_starts_at is not None
    assert reading.next_event_starts_at.isoformat() == "2026-07-04T23:00:00+00:00"


def test_events_fetch_handles_zero_events(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"page": {"totalElements": 0}}
    monkeypatch.setattr(collectors, "get_settings", _settings_with_ticketmaster_key)
    monkeypatch.setattr(collectors.httpx, "get", lambda *a, **k: _FakeResponse(payload))
    reading = collectors.fetch_events(_place())
    assert reading is not None
    assert reading.score == 0.0
    assert reading.event_count == 0
    assert reading.next_event_starts_at is None


def test_events_fetch_degrades_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise collectors.httpx.HTTPError("network down")

    monkeypatch.setattr(collectors, "get_settings", _settings_with_ticketmaster_key)
    monkeypatch.setattr(collectors.httpx, "get", boom)
    assert collectors.fetch_event_score(_place()) is None


def _settings_with_ticketmaster_key() -> Settings:
    return Settings(ticketmaster_api_key="test-key")

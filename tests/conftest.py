"""Shared pytest fixtures: in-memory DB, TestClient and offline collectors."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import collectors
from app.core import Settings, get_settings
from app.database import Base, get_db, seed_places
from app.main import app

_ENV_EXAMPLE = Path(__file__).resolve().parent.parent / ".env.example"


@pytest.fixture(autouse=True)
def example_env_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Load settings from .env.example (all keys blank) for every test.

    Keeps tests deterministic: real credentials in the developer's .env (or
    exported in the shell) must never reach the collectors.
    """
    for var in ("TOMTOM_API_KEY", "GOOGLE_PLACES_API_KEY", "TICKETMASTER_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", str(_ENV_EXAMPLE))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def clean_traffic_cache() -> Iterator[None]:
    """Keep the module-level traffic cache and budget from leaking across tests."""
    collectors.reset_traffic_cache()
    yield
    collectors.reset_traffic_cache()


@pytest.fixture
def db_session() -> Iterator[Session]:
    """A fresh in-memory SQLite session per test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = testing_session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    """TestClient wired to the in-memory session.

    Built without a context manager so the app lifespan (which would touch the
    real DB and start the scheduler) does not run.
    """

    def override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_client(client: TestClient, db_session: Session) -> TestClient:
    """A client whose database already contains the Bogotá seed."""
    seed_places(db_session)
    return client


@pytest.fixture
def offline_collectors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make scoring deterministic and network-free.

    Weather returns a fixed value; the key-gated collectors stay disabled, so
    activity comes from weather + the seeded popularity signal.
    """
    monkeypatch.setattr(
        collectors,
        "fetch_weather",
        lambda place: collectors.WeatherReading(
            score=50.0, temperature_c=18.0, precipitation_mm=0.0
        ),
    )
    monkeypatch.setattr(collectors, "fetch_traffic", lambda place: None)
    monkeypatch.setattr(collectors, "fetch_events", lambda place: None)
    monkeypatch.setattr(
        collectors,
        "fetch_air",
        lambda place: collectors.AirReading(score=70.0, pm2_5=12.5, european_aqi=30.0),
    )

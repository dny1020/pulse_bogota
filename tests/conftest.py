"""Shared pytest fixtures: in-memory DB, TestClient and offline collectors."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.collectors import events, traffic, weather
from app.database.database import Base, get_db
from app.database.seed import seed_places
from app.main import app


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
    monkeypatch.setattr(weather, "fetch_weather_score", lambda place: 50.0)
    monkeypatch.setattr(traffic, "fetch_traffic_score", lambda place: None)
    monkeypatch.setattr(events, "fetch_event_score", lambda place: None)

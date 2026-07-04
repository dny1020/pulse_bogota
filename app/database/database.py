"""SQLAlchemy engine, session factory and the FastAPI DB dependency."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# check_same_thread only matters for SQLite (used by the dev DB and tests).
_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Generator[Session]:
    """Yield a database session and ensure it is closed (FastAPI dependency)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

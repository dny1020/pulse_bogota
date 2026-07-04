"""FastAPI application entry point.

On startup it creates tables, seeds Bogotá places and (optionally) starts the
background scheduler. Run with: ``uvicorn app.main:app --reload``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import (
    activity,
    collectors,
    discover,
    engine,
    health,
    history,
    importer,
    places,
    query,
    top,
)
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.database.database import SessionLocal
from app.database.migrate import run_migrations
from app.database.seed import seed_places
from app.scheduler.jobs import shutdown_scheduler, start_scheduler

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialise DB + seed data and manage the scheduler lifecycle."""
    configure_logging()
    try:
        run_migrations()
        with SessionLocal() as db:
            inserted = seed_places(db)
    except Exception as exc:
        # DB or migration failure: fail fast with a clear log; the container
        # restart policy retries.
        log.error("startup_db_failed", error=str(exc))
        raise
    log.info("startup", seeded_places=inserted)

    settings = get_settings()
    scheduler = start_scheduler() if settings.scheduler_enabled else None
    try:
        yield
    finally:
        if scheduler is not None:
            shutdown_scheduler(scheduler)


app = FastAPI(title="pulse_bogota", version="0.1.0", lifespan=lifespan)

for router in (
    health.router,
    places.router,
    query.router,
    activity.router,
    history.router,
    top.router,
    engine.router,
    collectors.router,
    discover.router,
    importer.router,
):
    app.include_router(router)

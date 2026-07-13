"""FastAPI application entry point.

On startup it runs migrations, seeds Bogotá places and (optionally) starts the
background scheduler. Run with: ``uvicorn app.main:app --reload``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api import ALL_ROUTERS
from app.core import configure_logging, get_logger, get_settings
from app.database import SessionLocal, run_migrations, seed_places
from app.scheduler import shutdown_scheduler, start_scheduler

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


app = FastAPI(title="pulse_bogota", version=__version__, lifespan=lifespan)

for router in ALL_ROUTERS:
    app.include_router(router)

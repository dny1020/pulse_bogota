"""APScheduler wiring to recalculate scores on a fixed interval."""

from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.database import SessionLocal
from app.services.scoring import recalculate_all

log = get_logger(__name__)


def _recalculate_job() -> None:
    # Broad catch on purpose: a background job must log its failure and let
    # the scheduler try again on the next interval, never die silently.
    try:
        with SessionLocal() as db:
            count = recalculate_all(db)
        log.info("scheduled_recalculate", places=count)
    except Exception as exc:
        log.error("scheduled_recalculate_failed", error=str(exc))


def start_scheduler() -> BackgroundScheduler:
    """Start a background scheduler that recalculates scores periodically."""
    settings = get_settings()
    scheduler = BackgroundScheduler(timezone="America/Bogota")
    scheduler.add_job(
        _recalculate_job,
        "interval",
        minutes=settings.scheduler_interval_minutes,
        id="recalculate_scores",
        replace_existing=True,
    )
    scheduler.start()
    log.info("scheduler_started", interval_minutes=settings.scheduler_interval_minutes)
    return scheduler


def shutdown_scheduler(scheduler: BackgroundScheduler) -> None:
    """Stop the scheduler without waiting for running jobs."""
    scheduler.shutdown(wait=False)

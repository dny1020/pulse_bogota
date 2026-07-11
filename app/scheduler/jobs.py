"""APScheduler wiring to recalculate scores on a fixed interval."""

from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.database import SessionLocal
from app.services.anomaly import detect_anomalies
from app.services.forecast import train_model
from app.services.importer import import_osm_places
from app.services.scoring import recalculate_all, run_google_enrichment

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


def _osm_import_job() -> None:
    try:
        with SessionLocal() as db:
            result = import_osm_places(db)
        log.info("scheduled_osm_import", **result)
    except Exception as exc:
        log.error("scheduled_osm_import_failed", error=str(exc))


def _train_forecast_job() -> None:
    try:
        with SessionLocal() as db:
            result = train_model(db)
        log.info("scheduled_forecast_train", **result)
    except Exception as exc:
        log.error("scheduled_forecast_train_failed", error=str(exc))


def _google_refresh_job() -> None:
    try:
        with SessionLocal() as db:
            updated = run_google_enrichment(db)
        log.info("scheduled_google_refresh", updated=len(updated))
    except Exception as exc:
        log.error("scheduled_google_refresh_failed", error=str(exc))


def _anomaly_scan_job() -> None:
    try:
        with SessionLocal() as db:
            anomalies = detect_anomalies(db)
        log.info("scheduled_anomaly_scan", anomalies=len(anomalies))
    except Exception as exc:
        log.error("scheduled_anomaly_scan_failed", error=str(exc))


def start_scheduler() -> BackgroundScheduler:
    """Start the background jobs.

    Scoring runs on a fixed interval (default 15 min); OSM import, forecast
    training, Google refresh and anomaly scanning run weekly, each gated by its
    own settings flag.

    Weekly jobs use cron triggers (staggered on Sunday early morning) instead
    of interval ones: an interval trigger only fires N days after scheduler
    start, so any container restart within the week resets the countdown and
    the job never runs.
    """
    settings = get_settings()
    scheduler = BackgroundScheduler(timezone="America/Bogota")
    scheduler.add_job(
        _recalculate_job,
        "interval",
        minutes=settings.scheduler_interval_minutes,
        id="recalculate_scores",
        replace_existing=True,
    )
    if settings.osm_import_enabled:
        scheduler.add_job(
            _osm_import_job,
            "cron",
            day_of_week="sun",
            hour=3,
            id="import_osm_places",
            replace_existing=True,
        )
    if settings.forecast_enabled:
        scheduler.add_job(
            _train_forecast_job,
            "cron",
            day_of_week="sun",
            hour=4,
            id="train_forecast",
            replace_existing=True,
        )
    if settings.google_refresh_enabled and settings.google_places_api_key:
        scheduler.add_job(
            _google_refresh_job,
            "cron",
            day_of_week="sun",
            hour=5,
            id="google_refresh",
            replace_existing=True,
        )
    if settings.anomaly_detection_enabled:
        scheduler.add_job(
            _anomaly_scan_job,
            "cron",
            day_of_week="sun",
            hour=6,
            id="anomaly_scan",
            replace_existing=True,
        )
    scheduler.start()
    log.info(
        "scheduler_started",
        interval_minutes=settings.scheduler_interval_minutes,
        osm_import_enabled=settings.osm_import_enabled,
        forecast_enabled=settings.forecast_enabled,
    )
    return scheduler


def shutdown_scheduler(scheduler: BackgroundScheduler) -> None:
    """Stop the scheduler without waiting for running jobs."""
    scheduler.shutdown(wait=False)

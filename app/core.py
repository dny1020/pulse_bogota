"""Settings and logging: the two pieces every other module depends on.

Settings come from the environment / ``.env`` via pydantic-settings. Logging is
structlog on top of stdlib logging, so level and destination are configurable
(``LOG_LEVEL`` / ``LOG_FILE``) and the file handler survives container restarts
when the log directory is a mounted volume.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    External API keys are optional: when one is missing its collector simply
    returns no signal, and the activity score is computed from whatever is
    available (with a lower confidence).
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "pulse_bogota"
    database_url: str = "sqlite:///./pulse_bogota.db"

    # Logging: level name (DEBUG/INFO/WARNING/ERROR) and an optional file.
    # When log_file is blank, logs go to the console only.
    log_level: str = "INFO"
    log_file: str | None = None

    scheduler_enabled: bool = True
    scheduler_interval_minutes: int = 15

    # OSM/Overpass place importer (no key needed). The bounding box is
    # "south,west,north,east" and defaults to Bogotá.
    osm_import_enabled: bool = True
    osm_import_limit: int = 50
    osm_bbox: str = "4.47,-74.20,4.83,-73.99"
    # The catalogue grows over time: each run imports up to a limit derived from
    # how many places already exist (place_count * growth), capped at the max.
    osm_import_limit_max: int = 500
    osm_import_growth: float = 1.2

    default_city: str = "Bogotá"
    default_country: str = "Colombia"

    http_timeout_seconds: float = 10.0

    # Events collector: search radius around each place and how far ahead
    # to look for events that count towards the score.
    events_radius_km: int = 2
    events_window_hours: int = 24

    # Optional external API keys (blank -> collector disabled).
    tomtom_api_key: str | None = None
    google_places_api_key: str | None = None
    ticketmaster_api_key: str | None = None

    # TomTom is metered (2500 requests/day on the free tier) while scoring runs
    # every scheduler_interval_minutes over the whole catalogue, so calls grow
    # with the number of places. The cache decouples the two: a reading is
    # reused for traffic_cache_minutes instead of refetched on every run.
    # The daily budget is a backstop -- once the catalogue outgrows the cache
    # the collector goes quiet (and says so) instead of burning quota on 403s.
    traffic_cache_minutes: int = 60
    tomtom_daily_budget: int = 2400

    # Activity forecasting. A weekly job trains a model into forecast_model_path;
    # it is only used for a place once it has forecast_min_samples History rows,
    # otherwise the hourly-profile baseline is used (graceful degradation).
    forecast_enabled: bool = True
    forecast_min_samples: int = 200
    forecast_model_path: str = "./data/forecast_model.joblib"

    # Weekly Google Places refresh to keep ratings (popularity/discovery) fresh.
    google_refresh_enabled: bool = True

    # Anomaly detection: flag unusual days per place with a rolling z-score.
    anomaly_detection_enabled: bool = True
    anomaly_zscore_threshold: float = 3.0


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


_MAX_LOG_BYTES = 5_000_000
_BACKUP_COUNT = 3


def _resolve_level(name: str) -> int:
    """Map a level name to its logging constant; unknown names mean INFO."""
    return logging.getLevelNamesMapping().get(name.upper(), logging.INFO)


def _build_handlers(log_file: str | None) -> list[logging.Handler]:
    """Console handler always; add a rotating file handler when configured."""
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if not log_file:
        return handlers
    try:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                path, maxBytes=_MAX_LOG_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
            )
        )
    except OSError as exc:
        # A broken log path must not take the app down: keep console logging.
        logging.getLogger(__name__).warning("log file %s unavailable: %s", log_file, exc)
    return handlers


def configure_logging() -> None:
    """Configure structlog from Settings: level, console and optional file."""
    settings = get_settings()
    level = _resolve_level(settings.log_level)

    logging.basicConfig(
        format="%(message)s",
        level=level,
        handlers=_build_handlers(settings.log_file),
        force=True,
    )
    # httpx logs full request URLs at INFO, which leaks API keys passed as
    # query params (TomTom, Ticketmaster) into the log file. Keep it quiet.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        # Route events through stdlib logging so every handler (console and
        # file) receives them.
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str | None = None) -> Any:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)

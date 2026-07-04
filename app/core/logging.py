"""Structlog setup shared across the app.

Level and destination come from Settings (``LOG_LEVEL`` / ``LOG_FILE`` env
vars). Logs always go to the console; when ``LOG_FILE`` is set they are also
written to that file with rotation, so in Docker the log directory can be
mounted as a local volume and survive container restarts.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import structlog

from app.core.config import get_settings

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

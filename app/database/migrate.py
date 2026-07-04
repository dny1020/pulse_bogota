"""Run Alembic migrations programmatically (app lifespan or CLI).

There is no ``alembic.ini``: the script location is set here and the database
URL comes from Settings inside the migration env, same as the app. From the
terminal run ``uv run python -m app.database.migrate``.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.logging import get_logger

log = get_logger(__name__)

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def run_migrations() -> None:
    """Upgrade the configured database to the latest schema revision.

    The database URL comes from Settings inside the migration env, so this
    works the same in Docker (PostgreSQL) and bare local runs (SQLite).
    """
    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    command.upgrade(config, "head")
    log.info("migrations_applied")


if __name__ == "__main__":
    run_migrations()

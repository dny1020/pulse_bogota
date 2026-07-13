"""Alembic environment: reads the database URL from app Settings."""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# The app is not installed as a package (tool.uv.package = false), so put the
# project root on sys.path for the `alembic` CLI.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import get_settings  # noqa: E402
from app.database import Base  # noqa: E402  (importing it registers every table on Base.metadata)

config = context.config

# Reuse the app's DATABASE_URL unless one was passed explicitly (tests/CLI).
# `%` must be escaped because configparser interpolates it.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running against a live database."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the configured database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

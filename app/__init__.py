"""pulse_bogota: activity & discovery scoring API for places in Bogotá."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    # Single source of truth: the version declared in pyproject.toml.
    __version__ = version("pulse-bogota")
except PackageNotFoundError:
    # The app runs with `[tool.uv] package = false`, so it may not be installed
    # as a distribution (e.g. `uv run uvicorn ...`). Fall back to the current
    # release; keep this in sync with pyproject.toml on each bump.
    __version__ = "0.2.0"

"""pulse_bogota: activity & discovery scoring API for places in Bogotá."""

from __future__ import annotations

import tomllib
from pathlib import Path

# Single source of truth: the version in pyproject.toml. The file is present
# both in the repo (local dev/tests) and in the Docker image (copied to /app).
_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

try:
    with _PYPROJECT.open("rb") as fh:
        __version__: str = tomllib.load(fh)["project"]["version"]
except (OSError, KeyError):
    # Unexpected layout (e.g. pyproject.toml not shipped): report a neutral
    # version instead of crashing the app at import time.
    __version__ = "0.0.0"

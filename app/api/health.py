"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe: reports service status and the running API version."""
    return {"status": "ok", "version": __version__}

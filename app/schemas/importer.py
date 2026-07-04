"""Pydantic schemas for the importer endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class OsmImportResult(BaseModel):
    fetched: int
    created: int
    updated: int

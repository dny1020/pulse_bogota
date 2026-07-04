"""Import places from external sources on demand."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.schemas.importer import OsmImportResult
from app.services import importer as importer_service

router = APIRouter(prefix="/importer", tags=["importer"])


@router.post("/osm", response_model=OsmImportResult)
def import_osm(
    limit: int | None = Query(None, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    """Discover places on OpenStreetMap (Overpass) and upsert them."""
    return importer_service.import_osm_places(db, limit=limit)

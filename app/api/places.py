"""CRUD endpoints for places."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Place
from app.schemas.place import PlaceCreate, PlaceRead, PlaceUpdate
from app.services import places as places_service

router = APIRouter(prefix="/places", tags=["places"])


def _get_or_404(db: Session, place_id: int) -> Place:
    place = places_service.get_place(db, place_id)
    if place is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Place not found")
    return place


@router.get("", response_model=list[PlaceRead])
def list_places(db: Session = Depends(get_db)) -> list[Place]:
    return places_service.list_places(db)


@router.post("", response_model=PlaceRead, status_code=status.HTTP_201_CREATED)
def create_place(payload: PlaceCreate, db: Session = Depends(get_db)) -> Place:
    return places_service.create_place(db, payload)


@router.get("/{place_id}", response_model=PlaceRead)
def get_place(place_id: int, db: Session = Depends(get_db)) -> Place:
    return _get_or_404(db, place_id)


@router.put("/{place_id}", response_model=PlaceRead)
def update_place(place_id: int, payload: PlaceUpdate, db: Session = Depends(get_db)) -> Place:
    place = _get_or_404(db, place_id)
    return places_service.update_place(db, place, payload)


@router.delete("/{place_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_place(place_id: int, db: Session = Depends(get_db)) -> None:
    place = _get_or_404(db, place_id)
    places_service.delete_place(db, place)

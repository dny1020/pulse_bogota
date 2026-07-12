"""Store and query visitor feedback (the ground truth for the forecast model)."""

from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.database.models import Feedback

# A feedback level maps to the middle of its STATUS_BANDS range
# (engine/score.py); these become real training targets for the model.
LEVEL_TO_SCORE: dict[str, int] = {"quiet": 15, "moderate": 50, "busy": 85}


def create_feedback(db: Session, place_id: int, level: str) -> Feedback:
    """Persist one feedback report for a place.

    Args:
        db: Database session.
        place_id: The place the report is about (already validated to exist).
        level: One of ``"quiet"``, ``"moderate"``, ``"busy"``.

    Returns:
        The stored :class:`Feedback` row.
    """
    record = Feedback(place_id=place_id, level=level)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def feedback_for_place(db: Session, place_id: int) -> list[Feedback]:
    """Return a place's feedback, newest first."""
    stmt = (
        select(Feedback)
        .where(Feedback.place_id == place_id)
        .order_by(desc(Feedback.created_at), desc(Feedback.id))
    )
    return list(db.scalars(stmt))

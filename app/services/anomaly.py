"""Flag unusual activity readings per place with a simple z-score.

Cheap and model-free (plan.md item 4): for each place we compare every History
reading against that place's own mean and standard deviation, and flag the ones
whose absolute z-score crosses a threshold. Useful for spotting a surprisingly
busy (or dead) day without any training data.
"""

from __future__ import annotations

import statistics

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.models import Place
from app.schemas.anomaly import AnomalyPoint
from app.services.scoring import history_for_place

log = get_logger(__name__)

# Need at least this many readings before a z-score means anything.
_MIN_READINGS = 3


def detect_anomalies(
    db: Session,
    *,
    place_id: int | None = None,
    threshold: float | None = None,
) -> list[AnomalyPoint]:
    """Return readings whose z-score crosses ``threshold``.

    Args:
        db: Database session.
        place_id: Restrict to one place, or ``None`` to scan every place.
        threshold: Absolute z-score to flag; defaults to the configured value.

    Returns:
        Flagged readings, newest first within each place.
    """
    limit = threshold if threshold is not None else get_settings().anomaly_zscore_threshold
    place_ids = [place_id] if place_id is not None else [p.id for p in db.scalars(select(Place))]

    anomalies: list[AnomalyPoint] = []
    for pid in place_ids:
        rows = history_for_place(db, pid)  # newest first
        scores = [row.activity_score for row in rows]
        if len(scores) < _MIN_READINGS:
            continue
        mean = statistics.mean(scores)
        std = statistics.pstdev(scores)
        if std == 0:
            continue
        for row in rows:
            z_score = (row.activity_score - mean) / std
            if abs(z_score) >= limit:
                anomalies.append(
                    AnomalyPoint(
                        place_id=pid,
                        timestamp=row.created_at,
                        activity_score=row.activity_score,
                        z_score=round(z_score, 2),
                        mean=round(mean, 2),
                        std=round(std, 2),
                    )
                )
    return anomalies

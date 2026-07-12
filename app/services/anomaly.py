"""Flag unusual activity readings per place with a simple z-score.

Cheap and model-free: each History reading is compared against its own
``(hour, weekday)`` cell (same bucketing as the forecast baseline) so "busy at
8pm" is judged against other 8pm readings, not the whole day. Cells with too
few samples fall back to the place's global distribution — the original
behaviour — so sparse places still get anomaly detection.
"""

from __future__ import annotations

import statistics
from typing import Literal

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
        global_mean = statistics.mean(scores)
        global_std = statistics.pstdev(scores)

        cells: dict[tuple[int, int], list[int]] = {}
        for row in rows:
            key = (row.created_at.hour, row.created_at.weekday())
            cells.setdefault(key, []).append(row.activity_score)

        for row in rows:
            cell_scores = cells[(row.created_at.hour, row.created_at.weekday())]
            basis: Literal["hourly", "global"]
            if len(cell_scores) >= _MIN_READINGS:
                mean = statistics.mean(cell_scores)
                std = statistics.pstdev(cell_scores)
                basis = "hourly"
            else:
                mean, std, basis = global_mean, global_std, "global"
            if std == 0:
                continue
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
                        basis=basis,
                    )
                )
    return anomalies

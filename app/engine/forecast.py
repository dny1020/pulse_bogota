"""Pure activity-forecasting helpers.

Like ``engine/score.py`` these functions do no I/O, so they stay trivial to
unit-test and can be swapped for a trained model. The baseline predicts an
activity score for a future hour from the historical average of that
``(hour, weekday)`` cell; the same feature builder feeds the optional trained
model. Nothing here touches the database or the network.
"""

from __future__ import annotations

from datetime import datetime

import holidays

# Model feature vector, in a fixed order so the trained model always sees the
# same column layout at fit and predict time.
FEATURE_NAMES: list[str] = [
    "hour",
    "day_of_week",
    "is_weekend",
    "is_holiday",
    "latitude",
    "longitude",
    "recent_mean",
    "last_activity",
]

# Samples in a (hour, weekday) cell at which the baseline is "fully" confident.
_CONFIDENCE_TARGET = 4

# Colombian public holidays (lazily expands to whatever year is queried).
_CO_HOLIDAYS = holidays.Colombia()


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def is_colombian_holiday(moment: datetime) -> bool:
    """Return True when ``moment`` falls on a Colombian public holiday."""
    return moment.date() in _CO_HOLIDAYS


def baseline_profile(
    activity_by_time: list[tuple[datetime, int]],
) -> dict[tuple[int, int], tuple[float, int]]:
    """Average activity per ``(hour, weekday)`` cell.

    Args:
        activity_by_time: ``(created_at, activity_score)`` pairs from History.

    Returns:
        Mapping ``(hour, weekday) -> (mean_activity, sample_count)``.
    """
    buckets: dict[tuple[int, int], list[int]] = {}
    for moment, score in activity_by_time:
        buckets.setdefault((moment.hour, moment.weekday()), []).append(score)
    return {key: (sum(values) / len(values), len(values)) for key, values in buckets.items()}


def predict_baseline(
    profile: dict[tuple[int, int], tuple[float, int]],
    place_average: float | None,
    target: datetime,
) -> tuple[int, float]:
    """Predict activity for a future hour from the historical profile.

    Falls back to the place's overall average when the exact ``(hour, weekday)``
    cell has no samples, and to a neutral 50 with zero confidence when the place
    has no history at all. Confidence grows with the number of samples backing
    the prediction.

    Args:
        profile: Output of :func:`baseline_profile`.
        place_average: Mean activity across the place's history, or ``None``.
        target: The future hour to predict.

    Returns:
        Tuple of (activity_score 0-100, confidence 0-1).
    """
    cell = profile.get((target.hour, target.weekday()))
    if cell is not None:
        mean_activity, count = cell
        confidence = min(1.0, count / _CONFIDENCE_TARGET)
        return round(_clamp(mean_activity)), round(confidence, 2)
    if place_average is not None:
        return round(_clamp(place_average)), 0.2
    return 50, 0.0


def build_feature_row(
    *,
    target: datetime,
    latitude: float,
    longitude: float,
    recent_mean: float,
    last_activity: float,
) -> list[float]:
    """Build the model feature vector for ``target`` in ``FEATURE_NAMES`` order.

    Used at both training time (``target`` = a History row's timestamp) and
    inference time (``target`` = a future hour). Every feature is known ahead of
    time so the model can predict the future.
    """
    return [
        float(target.hour),
        float(target.weekday()),
        float(target.weekday() >= 5),
        float(is_colombian_holiday(target)),
        latitude,
        longitude,
        recent_mean,
        last_activity,
    ]

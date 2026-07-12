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
# same column layout at fit and predict time. The bundle on disk stores this
# list; a mismatch means the model was trained on an older layout and must not
# be used (services/forecast.py falls back to the baseline).
FEATURE_NAMES: list[str] = [
    "hour",
    "day_of_week",
    "is_weekend",
    "is_holiday",
    "latitude",
    "longitude",
    "recent_mean",
    "last_activity",
    "temperature_c",
    "precipitation_mm",
    "speed_ratio",
    "event_count",
]

# Neutral values when a raw signal was not captured (collector disabled or
# failed): Bogotá's typical temperature, no rain, free-flowing traffic, no
# events. Imputing keeps the vector shape fixed without dropping the sample.
_NEUTRAL_TEMPERATURE_C = 15.0
_NEUTRAL_PRECIPITATION_MM = 0.0
_NEUTRAL_SPEED_RATIO = 1.0
_NEUTRAL_EVENT_COUNT = 0.0

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
    temperature_c: float | None = None,
    precipitation_mm: float | None = None,
    speed_ratio: float | None = None,
    event_count: float | None = None,
) -> list[float]:
    """Build the model feature vector for ``target`` in ``FEATURE_NAMES`` order.

    Used at both training time (``target`` = a History row's timestamp, raw
    signals = that row's captured values) and inference time (``target`` = a
    future hour). Future raw signals are unknown, so inference passes the most
    recent captured values — a persistence assumption, like ``last_activity``.
    ``None`` raw signals are imputed with neutral values so the vector shape
    never changes.
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
        temperature_c if temperature_c is not None else _NEUTRAL_TEMPERATURE_C,
        precipitation_mm if precipitation_mm is not None else _NEUTRAL_PRECIPITATION_MM,
        speed_ratio if speed_ratio is not None else _NEUTRAL_SPEED_RATIO,
        float(event_count) if event_count is not None else _NEUTRAL_EVENT_COUNT,
    ]


def speed_ratio_from(
    current_speed_kmh: float | None, free_flow_speed_kmh: float | None
) -> float | None:
    """Ratio of current to free-flow speed (1.0 = traffic flows freely).

    Returns ``None`` when either speed is missing or free-flow is zero, so the
    caller can fall back to the neutral imputation.
    """
    if not current_speed_kmh or not free_flow_speed_kmh:
        return None
    return current_speed_kmh / free_flow_speed_kmh

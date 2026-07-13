"""Pure scoring and forecasting functions: activity, discovery and baseline.

Nothing here does I/O — no database, no network — so it stays trivial to
unit-test and can be swapped for a machine-learning model later. The same
feature builder feeds both the baseline and the optional trained model.
"""

from __future__ import annotations

from datetime import datetime

import holidays

# Base weights for the activity score (must sum to 1.0).
ACTIVITY_WEIGHTS: dict[str, float] = {
    "traffic": 0.40,
    "weather": 0.25,
    "events": 0.20,
    "popularity": 0.15,
}

# (inclusive upper bound, label) ordered ascending.
STATUS_BANDS: list[tuple[int, str]] = [
    (20, "Very Quiet"),
    (40, "Quiet"),
    (60, "Moderate"),
    (80, "Busy"),
    (100, "Very Busy"),
]

# Categories that reward exploration get a discovery bonus.
DISCOVERY_FRIENDLY: set[str] = {
    "cafe",
    "viewpoint",
    "library",
    "park",
    "bookstore",
    "garden",
    "trail",
    "plaza",
    "market",
    "museum",
    "cultural_center",
    "coworking",
}

# Model feature vector, in a fixed order so the trained model always sees the
# same column layout at fit and predict time. The bundle on disk stores this
# list; a mismatch means the model was trained on an older layout and must not
# be used (services.py falls back to the baseline).
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


# --- activity & discovery -------------------------------------------------


def compute_activity(components: dict[str, float | None]) -> tuple[int, float]:
    """Blend available signal components into an activity score.

    Missing components (``None``) are dropped and the remaining weights are
    renormalised, so the score always uses whatever data we have. Confidence is
    the share of total base weight that was available.

    Args:
        components: Mapping of signal name -> score in 0-100, or ``None``.

    Returns:
        Tuple of (activity_score 0-100, confidence 0-1).
    """
    available = {
        name: value
        for name, value in components.items()
        if value is not None and name in ACTIVITY_WEIGHTS
    }
    if not available:
        return 0, 0.0

    total_weight = sum(ACTIVITY_WEIGHTS[name] for name in available)
    blended = (
        sum(ACTIVITY_WEIGHTS[name] * _clamp(value) for name, value in available.items())
        / total_weight
    )
    confidence = total_weight / sum(ACTIVITY_WEIGHTS.values())
    return round(_clamp(blended)), round(confidence, 2)


def status_label(score: float) -> str:
    """Map an activity score (0-100) to a human-readable status label."""
    for upper, label in STATUS_BANDS:
        if score <= upper:
            return label
    return STATUS_BANDS[-1][1]


def popularity_score(rating: float | None, rating_count: int | None) -> float | None:
    """Derive a 0-100 popularity signal from place metadata, or ``None``.

    Combines how well a place is rated with how many people rate it. Returns
    ``None`` when no metadata exists so the activity score degrades gracefully.
    """
    if rating is None and rating_count is None:
        return None
    rating_part = (rating / 5 * 100) if rating is not None else 50.0
    volume_part = min(rating_count / 2000, 1.0) * 100 if rating_count is not None else 50.0
    return round(0.5 * rating_part + 0.5 * volume_part, 2)


def compute_discovery(
    activity_score: int | None,
    rating: float | None,
    rating_count: int | None,
    category: str,
) -> int:
    """Estimate how interesting/under-explored a place is (0-100).

    High when activity is low, ratings are good and the place is not
    over-reviewed -- i.e. independent of raw popularity.
    """
    activity = activity_score if activity_score is not None else 50
    calmness = 100 - _clamp(activity)
    rating_norm = (rating / 5 * 100) if rating is not None else 50.0
    obscurity = 50.0 if rating_count is None else _clamp(100 - (rating_count / 2000) * 100)
    category_bonus = 100.0 if category.lower() in DISCOVERY_FRIENDLY else 40.0

    score = 0.40 * calmness + 0.25 * rating_norm + 0.25 * obscurity + 0.10 * category_bonus
    return round(_clamp(score))


# --- forecasting ----------------------------------------------------------


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

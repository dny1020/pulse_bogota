"""Pure scoring functions for the activity and discovery engines.

These functions have no I/O so they are trivial to unit-test and to swap for a
machine-learning model later.
"""

from __future__ import annotations

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


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


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

"""Events collector — no provider wired yet, always returns ``None``.

The events signal (weight 0.20) stays in the engine: a ``None`` sub-score is
dropped and the remaining weights are renormalised, exactly like any other
disabled collector. When an events provider is chosen, implement the real
HTTP client here and add its key to ``core/config.py``.
"""

from __future__ import annotations

from app.database.models import Place


def fetch_event_score(place: Place) -> float | None:
    """Return a 0-100 score from nearby events, or ``None`` while disabled.

    Args:
        place: The place to score (unused until a provider is wired).

    Returns:
        Always ``None`` for now — the signal is dropped and the activity
        score is computed from the remaining collectors.
    """
    return None

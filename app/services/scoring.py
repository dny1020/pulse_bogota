"""Orchestrates collectors, computes activity scores and persists History.

The same functions back the manual ``/engine`` and ``/collector`` endpoints and
the background scheduler, so there is a single code path for scoring.
"""

from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.collectors import events, google, traffic, weather
from app.database.models import History, Place
from app.engine.score import compute_activity, popularity_score, status_label
from app.schemas.activity import ActivityRead


def score_place(db: Session, place: Place) -> History:
    """Run every collector for one place, compute its score, persist History.

    Besides the 0-100 sub-scores, the raw signal values (temperature, rain,
    speeds, rating snapshot) are stored so future ML features have real data.
    """
    traffic_reading = traffic.fetch_traffic(place)
    weather_reading = weather.fetch_weather(place)
    events_reading = events.fetch_events(place)
    social_score = popularity_score(place.rating, place.rating_count)

    activity, confidence = compute_activity(
        {
            "traffic": traffic_reading.score if traffic_reading else None,
            "weather": weather_reading.score if weather_reading else None,
            "events": events_reading.score if events_reading else None,
            "popularity": social_score,
        }
    )
    record = History(
        place_id=place.id,
        activity_score=activity,
        traffic_score=traffic_reading.score if traffic_reading else None,
        weather_score=weather_reading.score if weather_reading else None,
        event_score=events_reading.score if events_reading else None,
        social_score=social_score,
        temperature_c=weather_reading.temperature_c if weather_reading else None,
        precipitation_mm=weather_reading.precipitation_mm if weather_reading else None,
        current_speed_kmh=traffic_reading.current_speed_kmh if traffic_reading else None,
        free_flow_speed_kmh=traffic_reading.free_flow_speed_kmh if traffic_reading else None,
        event_count=events_reading.event_count if events_reading else None,
        next_event_starts_at=events_reading.next_event_starts_at if events_reading else None,
        place_rating=place.rating,
        place_rating_count=place.rating_count,
        confidence=confidence,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def recalculate_all(db: Session) -> int:
    """Score every place and return how many were processed."""
    places = list(db.scalars(select(Place)))
    for place in places:
        score_place(db, place)
    return len(places)


def latest_history(db: Session, place_id: int) -> History | None:
    """Return the most recent History row for a place, or ``None``."""
    stmt = (
        select(History)
        .where(History.place_id == place_id)
        .order_by(desc(History.created_at), desc(History.id))
        .limit(1)
    )
    return db.scalars(stmt).first()


def history_for_place(db: Session, place_id: int) -> list[History]:
    """Return a place's history, newest first."""
    stmt = (
        select(History)
        .where(History.place_id == place_id)
        .order_by(desc(History.created_at), desc(History.id))
    )
    return list(db.scalars(stmt))


def _activity_overview(db: Session) -> list[tuple[Place, History]]:
    """Pair each place with its latest history row (places that have one)."""
    overview: list[tuple[Place, History]] = []
    for place in db.scalars(select(Place)):
        record = latest_history(db, place.id)
        if record is not None:
            overview.append((place, record))
    return overview


def top_places(db: Session, *, busiest: bool, limit: int) -> list[ActivityRead]:
    """Return the quietest (or busiest) places by latest activity score."""
    overview = _activity_overview(db)
    overview.sort(key=lambda pair: pair[1].activity_score, reverse=busiest)
    return [
        ActivityRead(
            place_id=place.id,
            score=record.activity_score,
            status=status_label(record.activity_score),
            confidence=record.confidence,
        )
        for place, record in overview[:limit]
    ]


def run_signal_collector(db: Session, name: str) -> list[dict[str, object]]:
    """Run one signal collector for every place and report its raw values.

    Diagnostic only -- this does not persist History (use /engine/recalculate
    for that). Lets you confirm a collector / API key works independently.
    """
    collectors_by_name = {
        "weather": weather.fetch_weather_score,
        "traffic": traffic.fetch_traffic_score,
        "events": events.fetch_event_score,
    }
    collector = collectors_by_name[name]
    return [
        {"place_id": place.id, "name": place.name, "score": collector(place)}
        for place in db.scalars(select(Place))
    ]


def run_google_enrichment(db: Session) -> list[dict[str, object]]:
    """Refresh place metadata from Google Places and report what changed."""
    updated: list[dict[str, object]] = []
    for place in db.scalars(select(Place)):
        metadata = google.fetch_place_metadata(place)
        if not metadata:
            continue
        for field, value in metadata.items():
            if value is not None:
                setattr(place, field, value)
        updated.append({"place_id": place.id, "name": place.name, **metadata})
    db.commit()
    return updated

"""Application settings loaded from environment / .env via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    External API keys are optional: when one is missing its collector simply
    returns no signal, and the activity score is computed from whatever is
    available (with a lower confidence).
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "pulse_bogota"
    database_url: str = "sqlite:///./pulse_bogota.db"

    # Logging: level name (DEBUG/INFO/WARNING/ERROR) and an optional file.
    # When log_file is blank, logs go to the console only.
    log_level: str = "INFO"
    log_file: str | None = None

    scheduler_enabled: bool = True
    scheduler_interval_minutes: int = 15

    # OSM/Overpass place importer (no key needed). The bounding box is
    # "south,west,north,east" and defaults to Bogotá.
    osm_import_enabled: bool = True
    osm_import_limit: int = 50
    osm_bbox: str = "4.47,-74.20,4.83,-73.99"

    default_city: str = "Bogotá"
    default_country: str = "Colombia"

    http_timeout_seconds: float = 10.0

    # Events collector: search radius around each place and how far ahead
    # to look for events that count towards the score.
    events_radius_km: int = 2
    events_window_hours: int = 24

    # Optional external API keys (blank -> collector disabled).
    tomtom_api_key: str | None = None
    google_places_api_key: str | None = None
    ticketmaster_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()

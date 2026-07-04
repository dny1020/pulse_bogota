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

    scheduler_enabled: bool = True
    scheduler_interval_minutes: int = 15

    default_city: str = "Bogotá"
    default_country: str = "Colombia"

    http_timeout_seconds: float = 10.0

    # Optional external API keys (blank -> collector disabled).
    tomtom_api_key: str | None = None
    eventbrite_api_key: str | None = None
    google_places_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()

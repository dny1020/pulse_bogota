# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What the project is

`pulse_bogota` is a backend-only REST API (FastAPI) that helps you **discover quiet, interesting places in Bogotá without counting people**. It computes an **Activity Score (0–100)** from public signals (traffic, weather, events, popularity) so you can find a peaceful café, an uncrowded park, or a hidden viewpoint. A complementary **Discovery Score** rewards calm, well-rated, little-known spots — a quiet café can outrank a crowded landmark. MVP targets Bogotá but the design stays city-agnostic. `SPEC.md` is the product spec.

Tech stack: Python 3.13+ · FastAPI + Uvicorn · Pydantic v2 + pydantic-settings · SQLAlchemy 2.x · PostgreSQL (Docker/prod; SQLite for bare local dev + tests) · httpx · APScheduler · structlog · pytest · Ruff + Black · mypy.

## Commands

Dependencies and tasks are managed with **uv** (no `requirements.txt`; source of
truth is `pyproject.toml` + `uv.lock`). Common tasks are also in the `Makefile`.

```bash
# Setup
uv sync                                  # create .venv + install deps (incl. dev group)

# Run the API (Swagger at /docs); creates + seeds the DB on first start
uv run uvicorn app.main:app --reload

# Tests (offline — network is mocked)
uv run pytest                                   # full suite
uv run pytest tests/test_engine.py::test_status_label_boundaries   # single test

# Lint / format / type-check
uv run ruff check . && uv run black --check . && uv run mypy app
# or: make check
```

## Architecture (the big picture)

Layout: `app/{api,collectors,core,engine,scheduler,schemas,services,database}` + `tests/`. The non-obvious flow and rules:

- **Collectors → DB → Engine → API.** Each collector in `app/collectors/` (`weather`, `traffic`, `events`, `google`) has one responsibility and **never calls another collector**. `weather`/`traffic`/`events` return a reading dataclass (0–100 `score` + raw values); `fetch_*_score` wrappers expose just the score for the diagnostic endpoints. The scoring engine reads collector output, never the network directly. `app/collectors/osm.py` is different: it discovers new places via Overpass for the importer (`services/importer.py`, weekly job + `POST /importer/osm`, idempotent upsert on `Place.osm_id`).
- **Graceful degradation is core, not optional.** Collectors call real APIs. If an API key is missing (`traffic`/`events`/`google` are key-gated in `core/config.py`) or a request fails, the collector returns `None`; `engine/score.py:compute_activity` then renormalises the remaining weights and lowers `confidence` (= share of weight available). Only `weather` (Open-Meteo) works with no key. `events` uses the Ticketmaster Discovery API (count of events starting nearby within `EVENTS_WINDOW_HOURS`, saturating at 5). **Do not add mocks** — a disabled collector is just the real client waiting for a key/provider.
- **Pure engine.** `app/engine/score.py` is I/O-free (weights `traffic 0.40 / weather 0.25 / events 0.20 / popularity 0.15`, `status_label`, `popularity_score`, `compute_discovery`). Keep it pure so it stays unit-testable and swappable for an ML model later.
- **Single scoring path.** `app/services/scoring.py:score_place`/`recalculate_all` are called by the scheduler (`scheduler/jobs.py`, every 15 min), the `POST /engine/recalculate` endpoint, and indirectly drive `/top/*`. Don't duplicate scoring logic in routers. `POST /collector/{weather,traffic,events}` are **diagnostic** (return raw values, don't persist); `POST /collector/google` enriches `Place` metadata.
- **`Place` is mutable current state; `History` is append-only.** Every scoring run inserts one `History` row (component sub-scores + `activity_score` + `confidence`). Component→column map: traffic→`traffic_score`, weather→`weather_score`, events→`event_score`, popularity→`social_score`. History also stores **raw signals** for future ML: `temperature_c`, `precipitation_mm`, `current_speed_kmh`, `free_flow_speed_kmh`, `event_count`, `next_event_starts_at`, `place_rating`, `place_rating_count`.
- **Popularity & discovery use `Place.rating`/`Place.rating_count`** (extension beyond the original spec). These are seeded with real-ish values in `database/seed.py` and refreshed by the Google collector when a key is set.
- **Layering:** thin routers, logic in `app/services/`; every endpoint declares a `response_model` (route handlers return ORM objects, FastAPI serialises via the schema); DB sessions via `Depends(get_db)`; no global mutable state.
- **`/nearby`** uses a SQL bounding-box prefilter + Python haversine (`services/places.py`) — no PostGIS dependency.

## Conventions & constraints

- **DB schema** is managed by Alembic (`app/database/migrations`, run via `run_migrations()` in the `main.py` lifespan; CLI: `uv run python -m app.database.migrate` — there is no `alembic.ini`, migrations are configured programmatically and written by hand in `versions/`). Any model change needs a new migration — do not reintroduce `create_all()` in the app (tests still use it on in-memory SQLite). Seeding (`seed_places`) is idempotent (only runs on an empty table). Future work is tracked in `plan.md`, not in `SPEC.md`.
- **Portability:** PostgreSQL in Docker/prod, SQLite for bare local dev and tests — keep models/queries dialect-neutral so both engines behave the same (and PostGIS can drop in later).
- **Tests** use an in-memory SQLite session injected via a `get_db` override; the `client` fixture deliberately skips the app lifespan, and `offline_collectors` patches collectors so no test hits the network (`tests/conftest.py`).
- **Ruff config note:** `Depends()`/`Query()` in argument defaults are allowed via `extend-immutable-calls` in `pyproject.toml` — that's the intended FastAPI pattern, not a smell.
- **Tooling:** uv manages deps (`uv sync`/`uv run`, lockfile `uv.lock`). The app is **not** installed as a package (`[tool.uv] package = false`), so tests rely on `pythonpath = ["."]` in `pyproject.toml` — run `uv run pytest` (or `python -m pytest`), never the bare `pytest` console script from a non-root dir.
- **Docker/deploy:** `Dockerfile` (uv-based, arch-agnostic) + `docker-compose.yml` (two services: `api` + `db` PostgreSQL 17; data on the `pulse_pgdata` volume, `POSTGRES_PASSWORD` required in `.env`, `/health` healthcheck, `PULSE_IMAGE` overridable). Target is a Raspberry Pi 4 (arm64) pulling a GHCR image via CI/CD — the Pi pulls, never builds (`infra/compose.yaml` mirrors the same two-service stack; backups via `pg_dump` in `infra/backup.sh`).
- **Out of scope (don't add unasked):** frontend, auth, Redis/Celery, caching layer, vector DB, real ML model.

## Coding Style & Complexity Rules (Junior/Mid Developer Level)

- **Target Audience:** Write code that is simple, explicit, and easy to read/debug for a Junior or Mid-level developer. Prioritize clarity over optimization.
- **Complexity Limit:** Functions must be short (~≤40 lines where practical). Avoid metaprogramming, complex advanced decorators, multi-level dynamic abstractions, or multi-inheritance. Prefer explicit over clever.
- **Data Structures:** Use simple functions, Pydantic models for API layers, and standard Python native `dataclasses` or clean dicts for internal data passing.
- **Design Pattern:** Always favor composition over inheritance. Keep logic flat instead of deeply nested.
- **Documentation:** Enforce type hints everywhere. Include clean, straightforward Google-style docstrings on public functions to explain parameters and return values clearly.

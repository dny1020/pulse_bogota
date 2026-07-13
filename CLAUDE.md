# CLAUDE.md — pulse_bogota

FastAPI backend (no frontend) that finds **quiet, interesting places in Bogotá**
without counting people. Two numbers per place: **Activity Score** (0–100, from
traffic + weather + events + popularity) and **Discovery Score** (rewards calm,
well-rated, little-known spots). Product spec: `SPEC.md`. Future work: `plan.md`.

Stack: Python 3.13 · FastAPI · Pydantic v2 · SQLAlchemy 2 · PostgreSQL (prod) /
SQLite (dev + tests) · httpx · APScheduler · structlog · pytest · Ruff (lint + format) · Pyright.

## Commands

```bash
uv sync                               # setup (.venv + all deps)
uv run uvicorn app.main:app --reload  # run API (Swagger /docs; migrates + seeds on start)
uv run pytest                         # tests (offline — network is mocked)
uv run pytest tests/test_engine.py::test_status_label_boundaries  # single test
uv run ruff check . && uv run ruff format --check . && uv run pyright app tests  # same gate as CI
uv version --bump patch               # release: then commit + git tag vX.Y.Z
```

Always `uv run …` from the repo root: the app is not an installed package
(`package = false`), tests rely on `pythonpath = ["."]`.

## How it works (data flow)

**Collectors → DB → Engine → API.**

- `app/collectors/`: weather (Open-Meteo, keyless), traffic (TomTom), events
  (Ticketmaster), google (ratings), air (Open-Meteo air quality, keyless). One
  job each, never call each other. On a missing API key or a failed request
  they return `None` — **never add mocks**, a disabled collector is just the
  real client waiting for a key. Air is informative only: never joins the
  activity blend, its raw values (`pm2_5`, `european_aqi`) go to History.
- `app/engine/score.py` is pure (no I/O). Weights: traffic .40 / weather .25 /
  events .20 / popularity .15. Missing signals → renormalise weights and lower
  `confidence`. **Graceful degradation is the core design.**
- `app/services/scoring.py` is the ONLY scoring path (15-min scheduler job,
  `POST /engine/recalculate`, `/top/*`). Never re-implement scoring in routers.
- `Place` = mutable current state; `History` = append-only, one row per scoring
  run (sub-scores + raw signals for future ML). Column names: events→
  `event_score`, popularity→`social_score`.
- Forecast (`GET /forecast/{id}`, `GET /forecast/{id}/best-time`): pure
  hour×weekday baseline always works; a weekly job trains a GBM into
  `FORECAST_MODEL_PATH` (file on the `./data` volume, no DB table), used per
  place only with ≥ `FORECAST_MIN_SAMPLES` history rows AND better MAE than
  the baseline. Features = time + lags + raw signals (temp, rain, speed
  ratio, events) with neutral imputation; the bundle stores `feature_names`
  and a layout mismatch falls back to baseline. Visitor feedback
  (`POST /feedback/{id}`, quiet/moderate/busy) overrides training targets
  within ±90 min — real labels beat the system's own estimate. Anomalies
  (`GET /anomalies`) = on-demand z-score per (hour, weekday) cell, global
  fallback when the cell is sparse (`basis` field says which).
- `POST /collector/{weather,traffic,events}` are diagnostic only (nothing
  persisted). OSM importer (`collectors/osm.py` + `services/importer.py`)
  discovers new places via Overpass — weekly job + `POST /importer/osm`,
  idempotent upsert on `Place.osm_id`.
- `/nearby` = SQL bounding-box prefilter + Python haversine. No PostGIS.

## Rules & gotchas

- **Schema change ⇒ hand-written Alembic migration** in
  `app/database/migrations/versions/` (no `alembic.ini`; CLI:
  `uv run python -m app.database.migrate`). Never reintroduce `create_all()`
  in the app (tests still use it on in-memory SQLite). Seeding only runs on an
  empty table.
- Keep models/queries **dialect-neutral**: everything must work on both SQLite
  and PostgreSQL.
- Tests: in-memory SQLite via a `get_db` override; the `client` fixture skips
  the app lifespan; `offline_collectors` patches all network
  (`tests/conftest.py`).
- Thin routers, logic in `app/services/`, every endpoint declares a
  `response_model`, sessions via `Depends(get_db)`. `Depends()`/`Query()` in
  argument defaults is intentional (Ruff `extend-immutable-calls`).
- **Deploy is manual by design**: CI on push to `main` tests then publishes the
  image to GHCR; on the Raspberry Pi, `compose.yaml` + `.env` live only in
  `/opt/pulse_bogota/` (copy with `scp` when they change) and deploying is
  `docker compose pull && docker compose up -d`. Backups: manual `pg_dump`.
  Local Docker: `docker compose up --build -d` (api + PostgreSQL 17).
- Version has a single source: `pyproject.toml` (read with `tomllib` in
  `app/__init__.py`). Release with `make bump-*`.
- **Out of scope unless asked:** frontend, auth, Redis/Celery, caching layer,
  vector DB.
- Style: junior-readable, explicit over clever, functions ≲40 lines, type
  hints + Google-style docstrings on public functions.

# pulse_bogota — Software Specification

> Backend-only REST API to discover quiet, interesting places in Bogotá.

## 1. Vision

pulse_bogota is a backend-first REST API that estimates the activity level of
places from public signals. It does **not** count people; it estimates how
busy, quiet or interesting a place is and whether it is worth visiting now.

Two independent scores:

- **Activity Score (0–100):** estimated crowd level. `0 = Very Quiet`, `100 = Very Busy`.
- **Discovery Score (0–100):** how interesting a place is regardless of popularity.
  A small unknown café can outrank a famous attraction.

Target users: people seeking quiet places, tourists, remote workers and urban
explorers — plus apps, tourism platforms and recommendation engines as API
consumers.

## 2. Functional requirements

- **Places:** create, edit, delete, list, retrieve.
- **Activity engine:** compute Activity Score, Discovery Score and confidence
  from the available collectors. Missing collectors must never break the system.
- **History:** every recalculation is stored; historical data is never overwritten.
- **Discovery:** recommend quiet / hidden / random / surprise places, prioritising
  discovery over popularity.
- **Search:** keyword search, nearby search, top quiet, top busy.
- **Scheduler:** every 15 minutes collect weather/traffic/events, recompute scores
  and store history; weekly, import new places from OpenStreetMap.
- **Collectors:** independent modules that degrade gracefully when unconfigured.
- **Importer:** discover and store new places automatically from OSM/Overpass,
  idempotently (no duplicates on re-runs).

## 3. MVP scope (Phase 1) — delivered

Places CRUD · SQLAlchemy · History · Activity Score · Discovery Score ·
Scheduler · Bogotá seed · REST API + Swagger · tests.

Delivered after the MVP: Docker packaging, docker compose with two services
(api + PostgreSQL 17), CI/CD to GHCR, pull-based Raspberry Pi deployment
(`infra/`), `pg_dump` backups, configurable logging (`LOG_LEVEL` / `LOG_FILE`
env vars + local log volume), Alembic migrations, the OSM/Overpass place
importer, and raw signal capture in History.

Out of scope: frontend, authentication, machine learning. Future work lives in
`plan.md`, not in this spec.

## 4. API endpoints

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/health` | liveness |
| GET / POST | `/places` | list / create |
| GET / PUT / DELETE | `/places/{id}` | retrieve / update / delete |
| GET | `/history/{place_id}` | append-only history |
| GET | `/activity/{place_id}` | `{score, status, confidence}` |
| GET | `/top/quiet`, `/top/busy` | rankings |
| GET | `/search?q=` | keyword search |
| GET | `/nearby?lat=&lon=&radius=` | proximity |
| POST | `/engine/recalculate` | recompute all places |
| POST | `/collector/{weather,traffic,events,google}` | run one collector |
| POST | `/importer/osm` | discover & upsert OSM places (optional `limit`) |
| GET | `/discover/{random,hidden,quiet,surprise}` | optional: `city, max_score, category, limit, seed` |

`seed` uses `random.Random(seed)` for reproducible results. Every endpoint
exposes a Pydantic response model.

## 5. Activity engine

Weighted formula: **40% traffic · 25% weather · 20% events · 15% popularity**.

Unavailable signals are dropped and the remaining weights renormalised
automatically; `confidence` is the share of total weight that was available.

Labels: `0–20` Very Quiet · `21–40` Quiet · `41–60` Moderate · `61–80` Busy ·
`81–100` Very Busy.

## 6. Discovery score

Heuristic (no ML) from: activity score, rating, rating count and place category.
A calm, well-rated, little-reviewed place scores highest. Every recommendation
request is logged (kind, filters, recommended ids) via structlog.

## 7. Architecture & stack

FastAPI · PostgreSQL (Docker/prod; SQLite for bare local dev and tests) ·
SQLAlchemy 2.x · Pydantic v2 + pydantic-settings · APScheduler · httpx ·
structlog. Models and queries stay dialect-neutral so both engines behave the
same.

Layout: `app/{api,collectors,core,database,engine,scheduler,schemas,services}` +
`main.py`. Business logic lives in `services/`; routers stay thin. The pure
scoring functions live in `engine/score.py`.

## 8. Collectors, importer & external APIs

| Module | Source | API key |
| --- | --- | --- |
| Weather | Open-Meteo | none (always on) |
| Traffic | TomTom | required, else disabled |
| Events | Ticketmaster Discovery | required, else disabled |
| Metadata | Google Places | required, else disabled |
| Place importer | OSM Overpass | none (weekly job + `POST /importer/osm`) |

Each collector calls its real API; a missing key or failed request returns no
signal and lowers confidence — collectors never crash the API. Weather,
traffic and events return the sub-score **plus raw values** (temperature, rain
mm, current/free-flow speeds, event count and next event start) which are
persisted on every History row together with rating snapshots.

The events collector counts Ticketmaster events starting within
`EVENTS_RADIUS_KM` of the place over the next `EVENTS_WINDOW_HOURS`; the score
grows linearly and saturates at 5 events. Raw count and soonest start time are
kept as ML features.

The importer discovers named, discovery-friendly places (cafés, parks,
viewpoints, libraries…) inside the `OSM_BBOX` bounding box, capped at
`OSM_IMPORT_LIMIT` per run spread round-robin across categories, and upserts
keyed on `places.osm_id` (adopting same-name seeded places instead of
duplicating them). Imported places flow through the regular scoring path.

## 9. Coding standards

Intermediate Python level: thin routers, logic in services, dependency injection
for the DB session, complete type hints, Google-style docstrings, functions
~≤40 lines where practical, no mutable global state, composition over
inheritance, RESTful design.

## 10. Libraries

Managed with **uv** (`pyproject.toml` + `uv.lock`; no `requirements.txt`).
Runtime: `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`,
`sqlalchemy`, `alembic`, `psycopg[binary]`, `httpx`, `apscheduler`,
`structlog`. Dev group: `pytest`, `ruff`, `black`, `mypy`.

## 11. Acceptance criteria

- `uv sync` installs; `uv run uvicorn app.main:app --reload` starts cleanly.
- `docker compose up` starts api + PostgreSQL; data survives restarts.
- Schema managed by Alembic (`app/database/migrations`); the app runs
  `upgrade head` on startup, then inserts the Bogotá seed idempotently.
  PostgreSQL inside compose, SQLite when running bare or in tests.
- Swagger at `/docs`; every endpoint responds.
- Scheduler runs every 15 min; History persisted; Activity & Discovery scores
  returned; confidence reflects collector availability.
- Open-Meteo returns real data; missing API keys do not crash collectors.
- `pytest`, `ruff check .`, `black --check .` and `mypy app` all pass.

## 12. Verification

```bash
uv sync
uv run uvicorn app.main:app --reload   # bare local run (SQLite), Swagger at /docs
docker compose up -d                   # full stack: api + PostgreSQL
```

End-to-end: `GET /health` → ok · `GET /places` → seed · `POST /engine/recalculate`
→ History rows (weather real, others degrade, confidence < 1) · `GET /activity/{id}`
→ score/status/confidence · `GET /top/quiet` · `GET /discover/random?seed=123`
(reproducible).

```bash
uv run pytest && uv run ruff check . && uv run black --check . && uv run mypy app
```

## 13. AI constraints

- No paid libraries; do not replace approved libraries.
- REST conventions; thin routers; independent, interchangeable collectors.
- Deterministic randomness via `random.Random(seed)`.
- No auth, Kubernetes, Redis, Celery, RabbitMQ or microservices (plain docker
  compose is the delivered packaging — see §3).
- Prefer boring, stable and maintainable solutions.
- Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
- This spec describes the system **as built**; future work is tracked in
  `plan.md`.

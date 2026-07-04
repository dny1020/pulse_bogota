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
  and store history.
- **Collectors:** independent modules that degrade gracefully when unconfigured.

## 3. MVP scope (Phase 1) — delivered

Places CRUD · SQLite + SQLAlchemy · History · Activity Score · Discovery Score ·
Scheduler · Bogotá seed · REST API + Swagger · tests.

Out of scope: frontend, authentication, Docker, machine learning.

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
A calm, well-rated, little-reviewed place scores highest. May be replaced by an
ML model in a later phase.

## 7. Architecture & stack

FastAPI · SQLite · SQLAlchemy 2.x · Pydantic v2 + pydantic-settings ·
APScheduler · httpx · structlog.

Layout: `app/{api,collectors,core,database,engine,scheduler,schemas,services}` +
`main.py`. Business logic lives in `services/`; routers stay thin. The pure
scoring functions live in `engine/score.py`.

## 8. Collectors & external APIs (Phase 1)

| Collector | Source | API key |
| --- | --- | --- |
| Weather | Open-Meteo | none (always on) |
| Traffic | TomTom | required, else disabled |
| Events | — (no provider wired yet) | n/a — always disabled for now |
| Metadata | Google Places | required, else disabled |

Each collector calls its real API; a missing key or failed request returns no
signal and lowers confidence — collectors never crash the API. (An
OpenStreetMap/Overpass POI importer is a possible future addition, not Phase 1.)

## 9. Coding standards

Intermediate Python level: thin routers, logic in services, dependency injection
for the DB session, complete type hints, Google-style docstrings, functions
~≤40 lines where practical, no mutable global state, composition over
inheritance, RESTful design.

## 10. Libraries

Managed with **uv** (`pyproject.toml` + `uv.lock`; no `requirements.txt`).
Runtime: `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`,
`sqlalchemy`, `httpx`, `apscheduler`, `structlog`. Dev group: `pytest`, `ruff`,
`black`, `mypy`.

## 11. Acceptance criteria

- `uv sync` installs; `uv run uvicorn app.main:app --reload` starts cleanly.
- SQLite + tables created automatically (`create_all`; Alembic deferred); Bogotá
  seed inserted.
- Swagger at `/docs`; every endpoint responds.
- Scheduler runs every 15 min; History persisted; Activity & Discovery scores
  returned; confidence reflects collector availability.
- Open-Meteo returns real data; missing API keys do not crash collectors.
- `pytest`, `ruff check .`, `black --check .` and `mypy app` all pass.

## 12. Verification

```bash
uv sync
uv run uvicorn app.main:app --reload   # API up, SQLite + seed created, Swagger at /docs
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
- No auth, Docker/Kubernetes, Redis, Celery, RabbitMQ or microservices in Phase 1.
- Prefer boring, stable and maintainable solutions.
- Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).

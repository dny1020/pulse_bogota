# pulse_bogota

Backend-first REST API that estimates how busy a place is — without trying to
count people. It blends public signals into an **Activity Score (0–100)** and a
complementary **Discovery Score** so you can find quiet, interesting,
under-explored spots in Bogotá.

> "Find places worth visiting, not places everyone is visiting."

## Quickstart

Dependencies and tasks are managed with [uv](https://docs.astral.sh/uv/).

```bash
uv sync                       # create .venv and install all deps (incl. dev)
cp .env.example .env          # optional; all API keys are optional
uv run uvicorn app.main:app --reload
```

Or use the Makefile: `make install` then `make run`.

Open Swagger at <http://127.0.0.1:8000/docs>. On first start the DB is created
and seeded with ~14 real Bogotá places, then the scheduler begins recalculating
scores every 15 minutes.

## How scoring works

The **activity score** is a weighted blend: `traffic 40% · weather 25% · events
20% · popularity 15%`. Collectors call real APIs and **degrade gracefully**: if
an API key is missing or a request fails, that signal is dropped, the remaining
weights are renormalised, and `confidence` (share of weight available) drops.
Only Open-Meteo (weather) works with no key; add `TOMTOM_API_KEY`,
`EVENTBRITE_API_KEY` and/or `GOOGLE_PLACES_API_KEY` to `.env` to enable the rest.

The **discovery score** rewards calm, well-rated, little-known places, so a
quiet café can rank above a crowded landmark.

## Key endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness |
| GET/POST/PUT/DELETE | `/places`, `/places/{id}` | Place CRUD |
| GET | `/search?q=`, `/nearby?lat&lon&radius` | Find places |
| GET | `/activity/{place_id}` | `{score, status, confidence}` |
| GET | `/history/{place_id}` | Scoring history (append-only) |
| GET | `/top/quiet`, `/top/busy` | Rankings |
| POST | `/engine/recalculate` | Score all places now |
| POST | `/collector/{weather,traffic,events,google}` | Run one collector |
| GET | `/discover/{quiet,hidden,random,surprise}` | Discovery engine |

## Development

```bash
make check        # ruff + black --check + mypy + pytest
# or individually:
uv run pytest                                  # tests (offline; network is mocked)
uv run ruff check . && uv run black --check . && uv run mypy app
```

Run `make help` for all tasks.

## Docker

Compose runs two containers: the **api** and **PostgreSQL** (`db`). Set
`POSTGRES_PASSWORD` in `.env` first (see `.env.example`), then:

```bash
make docker-up        # docker compose up --build -d
make docker-logs      # follow logs
make docker-down      # stop
```

PostgreSQL data lives on the `pulse_pgdata` named volume, so the database
**and all History survive** restarts and image rebuilds. API keys and
`POSTGRES_PASSWORD` are read from `.env`; the api container waits for the db
healthcheck before starting.

Outside Docker (bare `uvicorn --reload` and the test suite) the app defaults
to SQLite — no PostgreSQL needed for local development. The models and queries
are dialect-neutral, so both engines behave the same.

## Deployment (next phase)

Target: **Raspberry Pi 4 (arm64)** pulling a prebuilt image, with CI/CD on
GitHub.

- The image is **architecture-agnostic** (`python:3.13-slim` + the multi-arch
  `uv` image), so CI builds it for `linux/arm64` with `docker buildx` and pushes
  to GitHub Container Registry (GHCR).
- The Pi never builds — it only pulls. Point Compose at the registry image and
  pull the new tag:

  ```bash
  export PULSE_IMAGE=ghcr.io/<owner>/pulse_bogota:latest
  docker compose pull && docker compose up -d
  ```

- `docker-compose.yml` already reads `PULSE_IMAGE` (defaults to a local build
  tag) and defines a `/health` healthcheck for safe rollouts.
- The deployment compose (`infra/compose.yaml`) runs the same api + PostgreSQL
  pair; backups use `pg_dump` (`infra/backup.sh`).

See `CLAUDE.md` for architecture and conventions, and `SPEC.md` for the product
spec.

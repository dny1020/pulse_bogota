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


Open Swagger at <http://127.0.0.1:8000/docs>. On first start Alembic migrations
create the schema and ~14 real Bogotá places are seeded; the scheduler then
recalculates scores every 15 minutes and imports new places from OpenStreetMap
weekly (or on demand via `POST /importer/osm`).

## How scoring works

The **activity score** is a weighted blend: `traffic 40% · weather 25% · events
20% · popularity 15%`. Collectors call real APIs and **degrade gracefully**: if
an API key is missing or a request fails, that signal is dropped, the remaining
weights are renormalised, and `confidence` (share of weight available) drops.
Only Open-Meteo (weather) works with no key; add `TOMTOM_API_KEY`,
`TICKETMASTER_API_KEY` and/or `GOOGLE_PLACES_API_KEY` to `.env` to enable the
rest. Events counts Ticketmaster events starting near each place within the
next `EVENTS_WINDOW_HOURS` (default 24h, radius `EVENTS_RADIUS_KM`, default
2 km).

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
| GET | `/forecast/{place_id}` | Hourly activity forecast (baseline or trained model) |
| GET | `/forecast/{place_id}/best-time` | Quietest & busiest predicted hour to visit |
| GET | `/anomalies[/{place_id}]` | Unusual readings (hour-aware z-score) |
| POST/GET | `/feedback/{place_id}` | Report / list real crowd levels (ground truth) |
| GET | `/top/quiet`, `/top/busy` | Rankings |
| POST | `/engine/recalculate` | Score all places now |
| POST | `/collector/{weather,traffic,events,air,google}` | Run one collector |
| POST | `/importer/osm` | Discover & store new places from OpenStreetMap |
| GET | `/discover/{quiet,hidden,random,surprise}` | Discovery engine |

Air quality (Open-Meteo, keyless) is informative only: it never joins the
activity blend, but its raw values (PM2.5, European AQI) are stored per scoring
run as future model features. Visitor feedback ("quiet"/"moderate"/"busy")
becomes the training target for History rows within ±90 minutes, so the
forecast model learns from real labels when they exist.

## Development

```bash
uv run pytest                                                  # tests (offline; network is mocked)
uv run ruff check . && uv run black --check . && uv run mypy app   # same gate as CI
uv version --bump patch                                        # then commit + git tag vX.Y.Z
```

## Docker

Compose runs two containers: the **api** and **PostgreSQL** (`db`). Set
`POSTGRES_PASSWORD` in `.env` first (see `.env.example`), then:

```bash
docker compose up --build -d
docker compose logs -f
docker compose down
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
  export PULSE_IMAGE=ghcr.io/dny1020/pulse_bogota:latest
  docker compose pull && docker compose up -d
  ```

- `docker-compose.yml` already reads `PULSE_IMAGE` (defaults to a local build
  tag) and defines a `/health` healthcheck for safe rollouts.
- Deployment is manual by design: the production `compose.yaml` and `.env` live
  only on the Pi (`/opt/pulse_bogota/`) and are copied over with `scp` when they
  change. After CI publishes a new image, deploy with
  `docker compose pull && docker compose up -d` on the Pi.
- Backups are manual too:
  `docker exec pulse-db pg_dump -U pulse pulse | gzip > backup.sql.gz`.

See `CLAUDE.md` for architecture and conventions, `SPEC.md` for the product
spec (as built), and `plan.md` for future work.

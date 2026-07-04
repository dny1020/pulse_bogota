.PHONY: help install run test lint format check docker-build docker-up docker-down docker-logs clean

help:
	@echo 'pulse_bogota — common tasks (managed with uv)'
	@echo ''
	@echo '  make install      sync all deps (incl. dev group) into .venv via uv'
	@echo '  make run          run the API locally with reload (uvicorn)'
	@echo '  make test         run the test suite'
	@echo '  make lint         ruff check + mypy'
	@echo '  make format       autoformat: ruff --fix + black'
	@echo '  make check        full gate: ruff + black --check + mypy + tests'
	@echo '  make docker-build build the Docker image'
	@echo '  make docker-up    build & start the stack (compose, detached)'
	@echo '  make docker-down  stop the stack'
	@echo '  make docker-logs  follow API logs'
	@echo '  make clean        remove caches and the local SQLite DB'

install:
	uv sync

run:
	uv run uvicorn app.main:app --reload

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run mypy app

format:
	uv run ruff check --fix .
	uv run black .

check:
	uv run ruff check .
	uv run black --check .
	uv run mypy app
	uv run pytest

docker-build:
	docker compose build

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f api

clean:
	rm -rf .ruff_cache .mypy_cache .pytest_cache
	rm -f pulse_bogota.db

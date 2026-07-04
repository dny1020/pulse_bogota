.PHONY: help test lint format check clean bump-minor bump-major

help:
	@echo 'pulse_bogota — common tasks'
	@echo ''
	@echo '  make test         run the test suite'
	@echo '  make lint         ruff check + mypy'
	@echo '  make format       autoformat: ruff --fix + black'
	@echo '  make check        full gate: ruff + black --check + mypy + tests'
	@echo '  make clean        remove caches and the local SQLite DB'
	@echo '  make bump-minor   bump minor version (0.1.0 -> 0.2.0)'
	@echo '  make bump-major   bump major version (0.1.0 -> 1.0.0)'

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

clean:
	rm -rf .ruff_cache .mypy_cache .pytest_cache
	rm -f pulse_bogota.db

bump-minor:
	awk -F'"' '/^version = /{split($$2,v,"."); $$0="version = \"" v[1] "." v[2]+1 ".0\""}1' pyproject.toml > pyproject.tmp && mv pyproject.tmp pyproject.toml

bump-major:
	awk -F'"' '/^version = /{split($$2,v,"."); $$0="version = \"" v[1]+1 ".0.0\""}1' pyproject.toml > pyproject.tmp && mv pyproject.tmp pyproject.toml

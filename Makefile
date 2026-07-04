.PHONY: help install test lint format check clean bump-minor bump-major

help:
	@echo 'pulse_bogota — common tasks'
	@echo ''
	@echo '  make install      uv sync (create .venv + install deps)'
	@echo '  make test         run the test suite'
	@echo '  make lint         ruff check + mypy'
	@echo '  make format       autoformat: ruff --fix + black'
	@echo '  make check        full gate: ruff + black --check + mypy + tests'
	@echo '  make clean        remove caches and the local SQLite DB'
	@echo '  make bump-minor   bump minor + git tag (0.1.0 -> 0.2.0)'
	@echo '  make bump-major   bump major + git tag (0.1.0 -> 1.0.0)'

install:
	uv sync

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
	@v=$$(python3 -c "import re;c=open('pyproject.toml').read();a,b,_=re.search(r'version = \"(\d+)\.(\d+)\.(\d+)\"',c).groups();print(f'{a}.{int(b)+1}.0')"); \
	sed -i "s/^version = \".*\"/version = \"$$v\"/" pyproject.toml; \
	git add pyproject.toml && git commit -m "bump: v$$v" && git tag "v$$v"

bump-major:
	@v=$$(python3 -c "import re;c=open('pyproject.toml').read();a,_,_=re.search(r'version = \"(\d+)\.(\d+)\.(\d+)\"',c).groups();print(f'{int(a)+1}.0.0')"); \
	sed -i "s/^version = \".*\"/version = \"$$v\"/" pyproject.toml; \
	git add pyproject.toml && git commit -m "bump: v$$v" && git tag "v$$v"

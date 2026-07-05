.PHONY: help install run test lint format check clean \
	docker-up docker-logs docker-down \
	bump-patch bump-minor bump-major

help:
	@echo 'pulse_bogota — common tasks'
	@echo ''
	@echo '  make install      uv sync (create .venv + install deps)'
	@echo '  make run          run the API with reload (Swagger at /docs)'
	@echo '  make test         run the test suite'
	@echo '  make lint         ruff check + mypy'
	@echo '  make format       autoformat: ruff --fix + black'
	@echo '  make check        full gate: ruff + black --check + mypy + tests'
	@echo '  make clean        remove caches and the local SQLite DB'
	@echo '  make docker-up    docker compose up --build -d'
	@echo '  make docker-logs  follow api container logs'
	@echo '  make docker-down  stop the compose stack'
	@echo '  make bump-patch   bump patch + git tag (0.1.0 -> 0.1.1)'
	@echo '  make bump-minor   bump minor + git tag (0.1.0 -> 0.2.0)'
	@echo '  make bump-major   bump major + git tag (0.1.0 -> 1.0.0)'

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

clean:
	rm -rf .ruff_cache .mypy_cache .pytest_cache
	rm -f pulse_bogota.db

docker-up:
	docker compose up --build -d

docker-logs:
	docker compose logs -f

docker-down:
	docker compose down

# One recipe for the three bumps: the part (patch/minor/major) comes from the
# target name ($@). Refuses to run on a dirty tree so the tag matches HEAD.
bump-patch bump-minor bump-major:
	@git diff --quiet && git diff --cached --quiet \
		|| { echo 'working tree not clean — commit or stash first'; exit 1; }
	@part=$(subst bump-,,$@); \
	v=$$(python3 -c "import re,sys;c=open('pyproject.toml').read();ma,mi,pa=map(int,re.search(r'version = \"(\d+)\.(\d+)\.(\d+)\"',c).groups());print({'major':f'{ma+1}.0.0','minor':f'{ma}.{mi+1}.0','patch':f'{ma}.{mi}.{pa+1}'}[sys.argv[1]])" $$part); \
	sed -i "s/^version = \".*\"/version = \"$$v\"/" pyproject.toml; \
	git add pyproject.toml && git commit -m "bump: v$$v" && git tag "v$$v"

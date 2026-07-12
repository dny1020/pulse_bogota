.PHONY: help test lint bump-patch bump-minor bump-major

help:
	@echo 'pulse_bogota — common tasks'
	@echo ''
	@echo '  make test        run the test suite'
	@echo '  make lint        ruff + black --check + mypy (same gate as CI)'
	@echo '  make bump-patch  0.2.0 -> 0.2.1, commit + git tag'
	@echo '  make bump-minor  0.2.0 -> 0.3.0, commit + git tag'
	@echo '  make bump-major  0.2.0 -> 1.0.0, commit + git tag'

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run black --check .
	uv run mypy app

bump-patch:
	uv version --bump patch
	git add pyproject.toml uv.lock
	git commit -m "bump: v$$(uv version --short)"
	git tag "v$$(uv version --short)"

bump-minor:
	uv version --bump minor
	git add pyproject.toml uv.lock
	git commit -m "bump: v$$(uv version --short)"
	git tag "v$$(uv version --short)"

bump-major:
	uv version --bump major
	git add pyproject.toml uv.lock
	git commit -m "bump: v$$(uv version --short)"
	git tag "v$$(uv version --short)"

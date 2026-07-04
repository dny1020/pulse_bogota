# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base

# Bring in the uv binary, pinned to match the local toolchain.
COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PATH="/app/.venv/bin:$PATH"

# Copied before the app code so dependency layers are cached unless deps change.
COPY pyproject.toml uv.lock ./

# CI gate: full dev toolchain, then lint + type-check + tests.
# Built with `--target test`; never ships.
FROM base AS test
RUN uv sync --frozen
COPY app ./app
COPY tests ./tests
COPY .env.example ./
RUN uv run ruff check . \
    && uv run black --check . \
    && uv run mypy app \
    && uv run pytest

# Runtime image (default target): runtime dependencies only, no dev group.
FROM base AS runtime
RUN uv sync --frozen --no-dev

COPY app ./app

EXPOSE 8000

# `python -m` puts the working dir on sys.path so `app.main` is importable.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# syntax=docker/dockerfile:1
FROM python:3.13-slim

# Bring in the uv binary, pinned to match the local toolchain.
COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PATH="/app/.venv/bin:$PATH"

# Install runtime dependencies only (skip the dev group) from the lockfile.
# Copied before the app code so this layer is cached unless deps change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app

EXPOSE 8000

# `python -m` puts the working dir on sys.path so `app.main` is importable.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

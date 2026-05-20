# syntax=docker/dockerfile:1.7
# Multi-stage Dockerfile for GRUVAX API
#
# Stage 1 (builder): installs Python deps via uv using a cache mount so that
#   subsequent builds hit the cache and complete in seconds rather than minutes.
# Stage 2 (runtime): lean python:3.13-slim image with a non-root gruvax user.

# ── Stage 1: builder ─────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

# Install uv (pinned for reproducibility)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /build

# Copy dependency manifests first so the dep layer caches between source changes
COPY pyproject.toml uv.lock ./

# Install dependencies into an isolated virtual environment
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copy the rest of the source and install the project itself
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.13-slim

# Create a non-root user (security baseline for 2026)
RUN groupadd --system gruvax && useradd --system --gid gruvax gruvax

WORKDIR /app

# Copy the virtual environment from the builder stage
COPY --from=builder /build/.venv /app/.venv

# Copy application source
COPY --from=builder /build/src /app/src

# Copy runtime artifacts
COPY migrations/ ./migrations/
COPY alembic.ini ./
COPY justfile ./

# TODO(plan-04): COPY frontend/dist/ ./static/
#   The frontend static files are built in plan 04 and served by FastAPI
#   StaticFiles.  This COPY will be uncommented once the frontend build lands.

# Ensure the venv's bin is first on PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

USER gruvax

EXPOSE 8000

# Run Alembic migrations then start Uvicorn
CMD ["sh", "-c", "alembic upgrade head && uvicorn gruvax.app:app --host 0.0.0.0 --port 8000"]

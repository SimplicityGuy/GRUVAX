# syntax=docker/dockerfile:1.7
# Multi-stage Dockerfile for GRUVAX API + SPA
#
# Stage 1 (frontend-builder): Node.js image that runs npm ci + vite build.
#   Output: frontend/dist/ (built SPA assets).
#
# Stage 2 (python-builder): installs Python deps via uv with a cache mount so
#   that subsequent builds hit the layer cache (seconds, not minutes).
#
# Stage 3 (runtime): lean python:3.14-slim image with a non-root gruvax user.
#   Receives the .venv from stage 2 and the built SPA static/ from stage 1.
#   FastAPI StaticFiles serves the SPA at / (mounted after all /api routers).

# ── Stage 1: frontend build ───────────────────────────────────────────────────
FROM node:22-slim AS frontend-builder

WORKDIR /frontend-build

# Copy dependency manifests first to maximize npm layer cache
COPY frontend/package.json frontend/package-lock.json ./

RUN npm ci

# Copy all frontend source
COPY frontend/ ./

# Build: emits dist/ (note: vite.config.ts sets outDir: '../static' for dev use,
# but inside this Docker stage the working dir is /frontend-build, so dist/
# lands at /frontend-build/dist — we COPY it in stage 3 explicitly)
RUN npm run build -- --outDir dist

# ── Stage 2: Python dependency builder ───────────────────────────────────────
FROM python:3.14-slim AS python-builder

# Install uv (latest from the official image)
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

# ── Stage 3: runtime ──────────────────────────────────────────────────────────
FROM python:3.14-slim

# Create a non-root user (security baseline for 2026)
RUN groupadd --system gruvax && useradd --system --gid gruvax gruvax

WORKDIR /app

# Copy the virtual environment from the Python builder stage
COPY --from=python-builder /build/.venv /app/.venv

# Copy application source
COPY --from=python-builder /build/src /app/src

# Copy the built SPA into static/ — FastAPI StaticFiles mounts this at /
# (guarded: only mounts if the directory exists, see app.py)
COPY --from=frontend-builder /frontend-build/dist ./static/

# Copy runtime artifacts
COPY migrations/ ./migrations/
COPY alembic.ini ./
COPY justfile ./

# Ensure the venv's bin is first on PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

USER gruvax

EXPOSE 8000

# Run Alembic migrations then start Uvicorn
CMD ["sh", "-c", "alembic upgrade head && uvicorn gruvax.app:app --host 0.0.0.0 --port 8000"]

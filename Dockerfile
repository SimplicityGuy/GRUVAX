# syntax=docker/dockerfile:1.7
# Multi-stage Dockerfile for GRUVAX API + SPA
#
# Stage 1 (frontend-builder): Node.js image that runs npm ci + vite build.
#   Output: /static/ (built SPA assets at the vite outDir '../static' path).
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

# Copy the design tokens file — main.tsx imports it as '../../design/gruvax-design-tokens.css'
# which resolves relative to the frontend/src/ dir → ../../design/ = one level above /frontend-build.
# We place the design directory at that location so the relative path resolves.
COPY design/ /design/

# Build: vite.config.ts sets outDir: '../static' relative to the frontend/ workdir.
# In this stage workdir is /frontend-build, so '../static' → /static.
# Stage 3 COPYs from /static into the runtime image.
RUN npm run build

# ── Stage 2: Python dependency builder ───────────────────────────────────────
FROM python:3.14-slim AS python-builder

# Install uv (latest from the official image)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /build

# Copy dependency manifests first so the dep layer caches between source changes
# README.md is referenced by pyproject.toml and must be present for uv to build the package
COPY pyproject.toml uv.lock README.md ./

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
COPY --from=frontend-builder /static ./static/

# Copy runtime artifacts
COPY migrations/ ./migrations/
COPY alembic.ini ./
COPY justfile ./
# fixtures/ ships the committed, PII-free dev assets (boundaries.yaml is seeded
# into gruvax.cube_boundaries by the entrypoint; the local collection CSV is NOT
# in fixtures/ and stays gitignored, so it never enters the image).
COPY fixtures/ ./fixtures/

# Copy and make the entrypoint script executable (done as root before USER switch)
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Ensure the venv's bin is first on PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

USER gruvax

EXPOSE 8000

# Run Alembic migrations then start Uvicorn via entrypoint script.
# Using a dedicated script ensures PATH=/app/.venv/bin is set even when
# the Docker runtime (e.g. Rancher Desktop on macOS) injects the host PATH.
CMD ["/app/docker-entrypoint.sh"]

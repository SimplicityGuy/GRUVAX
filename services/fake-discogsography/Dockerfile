# syntax=docker/dockerfile:1.7
#
# Compose-sibling fake discogsography for dev + init-sync flow (Plan 01-05, D-15/D-16).
#
# Build context is the REPO ROOT (compose.yaml sets `build.context: .`) so the
# gruvax package source is in scope. server.py imports the canonical
# `gruvax._internal.fake_discogsography` module — there is intentionally NO
# copy of the canonical module under services/ (D-15: single-source mandate).
#
# Why install the gruvax package rather than a minimal `pip install fastapi`?
# - The canonical module's import path is `gruvax._internal.fake_discogsography`,
#   so the gruvax package must be importable inside the runtime container.
# - All required runtime deps (fastapi, pyyaml, pydantic, uvicorn) are already
#   in the gruvax core dependency set — no `[fake]` extra needed for this image.
#
# This Dockerfile is intentionally NOT multi-stage — the fake is dev-only and
# image size is not a constraint. Keeping the build dead-simple favors
# readability + faster CI iteration on compose-smoke.

FROM python:3.14-slim AS runtime

# uv is installed for the package install only; runtime invokes uvicorn directly.
# Test-fixture image; intentionally tracks latest uv to match astral-sh/uv:latest in the api image.
# hadolint ignore=DL3013
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy the gruvax package source first so the dependency layer caches between
# source-only changes (BuildKit pattern from the main Dockerfile).
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

# Install gruvax + its runtime dependencies in system site-packages so the
# `gruvax._internal.fake_discogsography` import resolves at runtime. The
# Dockerfile intentionally uses `uv pip install --system` (not a venv) — this
# image runs ONE process and benefits from the simpler import path.
RUN uv pip install --system --no-cache .

# Copy the sibling entry script + seed last so source/seed changes don't
# invalidate the install layer above.
COPY services/fake-discogsography/server.py services/fake-discogsography/seed.yaml ./

# Create a non-root user (2026 baseline expectation per the GRUVAX stack
# infrastructure convention — mirrors the main Dockerfile's gruvax user).
# CWE-250: never run the container process as root.
RUN groupadd --system fake && useradd --system --gid fake --no-create-home --shell /usr/sbin/nologin fake \
    && chown -R fake:fake /app
USER fake

EXPOSE 8004

HEALTHCHECK --interval=30s --timeout=5s --retries=5 --start-period=10s \
    CMD python -c "import urllib.request as u; req = u.Request('http://127.0.0.1:8004/api/user/collection?limit=1', headers={'Authorization': 'Bearer dscg_dev_seed'}); u.urlopen(req).read()" \
    || exit 1

# uvicorn serves the in-process FastAPI app exposed at module-level `app`
# (see server.py). --host 0.0.0.0 so the api container can reach it via
# the internal Compose network DNS as `fake-discogsography:8004`.
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8004"]

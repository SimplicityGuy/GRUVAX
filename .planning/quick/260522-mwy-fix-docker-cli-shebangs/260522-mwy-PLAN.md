---
quick_id: 260522-mwy
slug: fix-docker-cli-shebangs
type: quick
date: 2026-05-22
description: Fix runtime Docker venv shebangs so console scripts (gruvax-set-pin) run directly
---

# Quick Task 260522-mwy: Fix Docker console-script shebangs

## Problem

`docker compose exec -it gruvax-api gruvax-set-pin` fails with:

```
exec /app/.venv/bin/gruvax-set-pin: no such file or directory
```

The script file *exists*, but its shebang is `#!/build/.venv/bin/python3` — the
build-stage venv path, which does not exist in the runtime image. `uv sync` bakes
an absolute interpreter shebang into every entry-point script it generates
(`gruvax`, `gruvax-set-pin`). The Dockerfile builds the venv at `/build/.venv`
(Stage 2, `WORKDIR /build`) then copies it to `/app/.venv` (Stage 3), so the
shebang interpreter path is stale at runtime.

The entrypoint (`docker-entrypoint.sh`) already dodges this for alembic/uvicorn
via the `python -m` pattern (Phase 01-04 finding), but the standalone console
scripts were left broken — which surfaced when the owner tried to reset the admin
PIN during the Phase 05 / 05-05 human-verify checkpoint.

## Fix

Build the venv at its final runtime path so shebangs are correct from the start:

1. Stage 2 (`python-builder`): add `ENV UV_PROJECT_ENVIRONMENT=/app/.venv` before
   the `uv sync` calls, so `uv` writes the venv (and `#!/app/.venv/bin/python3`
   shebangs) to `/app/.venv`.
2. Stage 3 (runtime): copy from the new path —
   `COPY --from=python-builder /app/.venv /app/.venv`.

`PYTHONPATH=/app/src` (already set) covers the editable-install `.pth` path
mismatch, and the entrypoint's `python -m` calls remain valid.

## Tasks

### Task 1: Repoint the builder venv to /app/.venv
- **files:** `Dockerfile`
- **action:** Add `ENV UV_PROJECT_ENVIRONMENT=/app/.venv` in Stage 2; update the
  Stage 3 `COPY --from=python-builder` source to `/app/.venv`.
- **verify:** Rebuild the api image; `docker compose exec -T gruvax-api head -1
  /app/.venv/bin/gruvax-set-pin` shows `#!/app/.venv/bin/python3`; a piped invalid
  PIN (`printf 'abc\n' | gruvax-set-pin`) reaches the 4-digit validation message
  (proving the script runs end-to-end) without setting a PIN or touching the DB.
- **done:** `docker compose exec -it gruvax-api gruvax-set-pin` reaches the
  `Enter new PIN (4 digits):` prompt.

## Out of scope
- No change to `docker-entrypoint.sh` (its `python -m` calls already work).
- No change to the console-script definitions in `pyproject.toml`.

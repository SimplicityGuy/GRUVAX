---
quick_id: 260522-mwy
slug: fix-docker-cli-shebangs
type: quick
date: 2026-05-22
status: complete
---

# Quick Task 260522-mwy: Fix Docker console-script shebangs — SUMMARY

## What changed

`Dockerfile` (2 edits):
1. Stage 2 (`python-builder`): added `ENV UV_PROJECT_ENVIRONMENT=/app/.venv` before
   the `uv sync` calls so `uv` builds the venv (and its entry-point shebangs) at the
   final runtime path.
2. Stage 3 (runtime): `COPY --from=python-builder /build/.venv` → `/app/.venv`.

## Why

`uv sync` writes absolute interpreter shebangs into the console scripts it
generates (`gruvax`, `gruvax-set-pin`). Building the venv at `/build/.venv` then
copying it to `/app/.venv` left those shebangs pointing at the missing
`/build/.venv/bin/python3`, so `docker compose exec -it gruvax-api gruvax-set-pin`
failed with `exec ...: no such file or directory`. Building the venv at
`/app/.venv` makes the shebangs correct at runtime. The Phase 01-04 `python -m`
workaround in `docker-entrypoint.sh` covered alembic/uvicorn but not the
standalone CLIs; this closes that gap.

## Verification (image rebuilt, container recreated)

| Check | Result |
|-------|--------|
| `docker compose build gruvax-api` | ✓ built |
| `head -1 /app/.venv/bin/gruvax-set-pin` | `#!/app/.venv/bin/python3` ✓ |
| `head -1 /app/.venv/bin/gruvax` | `#!/app/.venv/bin/python3` ✓ |
| `command -v gruvax-set-pin` (container PATH) | `/app/.venv/bin/gruvax-set-pin` ✓ |
| `printf 'abc\n' \| ... gruvax-set-pin` | reaches prompt → "PIN must be exactly 4 numeric digits", exit 1 (no PIN set, no DB write) ✓ |

Net result: `docker compose exec -it gruvax-api gruvax-set-pin` now reaches the
`Enter new PIN (4 digits):` prompt and works interactively.

## Notes / follow-ups
- `PYTHONPATH=/app/src` (already set) covers the editable-install `.pth` path
  mismatch; imports resolve normally.
- The `python -m` invocations in `docker-entrypoint.sh` remain valid and unchanged.
- Executed inline (no subagent/worktree) — trivial 2-line config fix, fully
  specified; keeps the quick-task tracking (PLAN/SUMMARY + STATE row + atomic commit).

## Self-Check: PASSED

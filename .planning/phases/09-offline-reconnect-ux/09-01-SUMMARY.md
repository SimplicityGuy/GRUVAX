---
phase: 09-offline-reconnect-ux
plan: "01"
subsystem: backend/sse
tags: [sse, reconnect, jitter, offline, pitfall-36]
dependency_graph:
  requires: []
  provides: [retry-jitter-on-sse-connect]
  affects: [EventSource-reconnect-interval]
tech_stack:
  added: []
  patterns: [random.randint jitter on ServerSentEvent initial frame]
key_files:
  created: []
  modified:
    - src/gruvax/api/events.py
decisions:
  - "retry: jitter range 2000-8000 ms (per plan spec, PITFALLS 36)"
  - "ping=15 keepalive unchanged — orthogonal to per-connection retry interval"
  - "No /healthz reconnect probe added (CONTEXT Claude-Discretion decision)"
metrics:
  duration: "<5 minutes"
  completed: "2026-06-02"
  tasks_completed: 1
  files_modified: 1
requirements-completed: [OFF-03]
---

# Phase 9 Plan 01: SSE Reconnect Jitter Summary

**One-liner:** Per-connection `retry:` jitter (2000-8000 ms) on the SSE generator's initial frame prevents a thundering-herd reconnect storm after server restart.

## What Was Built

Added `import random` and a `retry_ms = random.randint(2000, 8000)` computation to the SSE `generator()` function in `src/gruvax/api/events.py`. The initial `ServerSentEvent` yield now passes `retry=retry_ms`, telling each browser's `EventSource` a distinct reconnect interval. When `gruvax-api` restarts (nightly Compose redeploy or manual), the ~30 connected kiosk+browser clients spread their reconnects over a 2-8s window instead of all hammering the single Uvicorn worker at the browser-default 3s simultaneously.

The `ping=15` keepalive on `EventSourceResponse` is untouched — it is orthogonal to the per-connection reconnect interval (PITFALLS 8 vs 36). The `while True` loop, `request.is_disconnected()` check, `asyncio.wait_for(q.get(), timeout=1.0)`, and `bus.unsubscribe(q)` cleanup in `finally` are all unchanged.

## Tasks

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Emit jittered retry: on the SSE generator's initial frame | 8f7ba9c | src/gruvax/api/events.py |

## Verification

- Source assertions: `import random`, `random.randint(2000, 8000)`, and `retry=retry_ms` all present in `events.py`; `ping=15` retained; one `bus.unsubscribe(q)` in `finally`
- `uv run ruff check src/gruvax/api/events.py` — clean
- `uv run mypy src/gruvax/api/events.py` — no issues
- `pytest tests -k "events or event_bus" -q` — 11 passed (run from main repo with `.env`)

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes. The `retry_ms` value is non-sensitive (by-design client-readable per T-09-03 accepted). No new threat surface beyond what is in the plan's threat model.

## Self-Check

- [x] `src/gruvax/api/events.py` modified — FOUND
- [x] Commit 8f7ba9c exists — FOUND
- [x] SUMMARY.md at correct path

## Self-Check: PASSED

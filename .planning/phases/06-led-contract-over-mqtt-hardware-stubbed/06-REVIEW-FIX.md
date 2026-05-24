---
phase: 06-led-contract-over-mqtt-hardware-stubbed
fixed_at: 2026-05-24T04:18:56Z
review_path: .planning/phases/06-led-contract-over-mqtt-hardware-stubbed/06-REVIEW.md
iteration: 1
findings_in_scope: 13
fixed: 13
skipped: 0
status: all_fixed
---

# Phase 6: Code Review Fix Report

**Fixed at:** 2026-05-24T04:18:56Z
**Source review:** .planning/phases/06-led-contract-over-mqtt-hardware-stubbed/06-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 13 (4 Critical + 9 Warning; Info findings IN-01..IN-05 are out of scope for `fix_scope: critical_warning`)
- Fixed: 13
- Skipped: 0

## Quality Gate (post-fix, full suite)

All three required gates were run inside the isolated worktree after all fixes were applied and all pass:

| Gate | Command | Result |
|------|---------|--------|
| Tests | `uv run pytest tests/ -q --tb=short` | **PASS** — 326 tests, 0 failures, 0 errors, 9 skipped (exit 0) |
| Type check | `uv run mypy --strict src/gruvax/` | **PASS** — Success, 49 source files, no issues |
| Frontend build | `npm --prefix frontend run build` | **PASS** — `tsc -b` clean + `vite build` succeeded (one advisory chunk-size warning, non-fatal) |

No `--no-verify` was used on any commit. The shared dev DB was on head throughout (no migration round-trip left it off head, so no `alembic upgrade head` re-run was required).

## Fixed Issues

### CR-01: Fire-and-forget asyncio tasks are garbage-collected mid-flight

**Files modified:** `src/gruvax/api/illuminate.py`, `src/gruvax/app.py`
**Commit:** fa35d26
**Applied fix:** Added an app-scoped strong-reference set `app.state.background_tasks` (created in the lifespan) plus a module-level fallback set in `illuminate.py`. Introduced a `_spawn(coro, request)` helper that adds each fire-and-forget task to the set and discards it via `add_done_callback`, mirroring the `HighlightRegistry` discipline. The two `asyncio.create_task` call sites in the illuminate endpoint and the startup ambient-publish task now hold strong references so the GC cannot cancel an in-flight publish. The existing `test_fan_out_count` (which patches `create_task`) still passes.

### CR-02: Span brightness ceiling hardcoded to 128 silently discards admin values above 128

**Files modified:** `src/gruvax/mqtt/publishers.py`
**Commit:** 0aa4287
**Applied fix:** Changed the `clamp_brightness(..., 128)` ceiling to `clamp_brightness(..., 255)` in both `fan_out_illuminate` (span tier) and `run_diagnostic` (span state). The span default value remains 128, but the ceiling is now the 8-bit hardware cap, so an admin-configured span brightness up to 255 is honoured. Span and active ceilings are now separately configurable as required by the success criterion.

### CR-03: Diagnostic's transient subscribe drains the shared message iterator and is not shutdown-safe

**Files modified:** `src/gruvax/mqtt/publishers.py`
**Commit:** 36a1bac
**Applied fix:** Added a per-client concurrency guard (`client._gruvax_diag_active`) around the `status/#` subscribe window so at most one diagnostic owns the single shared `client.messages` iterator at a time; a second concurrent diagnostic logs a warning and skips the subscribe window rather than racing for inbound messages. The existing `asyncio.timeout(5.0)` bound keeps the window finite and cancelable (CancelledError at shutdown still runs the `finally` that unsubscribes and clears the guard). The guard uses `getattr(...) is True` (not truthiness) so it is resilient to mock objects that auto-create truthy attributes.
**Requires human verification:** This is a concurrency-control change; the single-process correctness is covered by tests, but the intended behaviour under genuinely concurrent diagnostics on a live broker should be confirmed manually.

### CR-04: Diagnostic leaves every cube dark — retained-hygiene regression (D-12 / D-20 / LED-11)

**Files modified:** `src/gruvax/mqtt/publishers.py`, `tests/unit/test_led_admin_endpoints.py`
**Commit:** bb7f94a
**Applied fix:** Added `await publish_ambient(client, pool, settings_cache)` as the final step of `run_diagnostic` (after the `status/#` subscribe window), so the diagnostic ends in the idle ambient baseline instead of leaving every cube's retained `state/*` cleared (dark). This restores the LED-11/D-20 invariant that every cube shows the idle ambient colour when no highlight is active, and makes the post-diagnostic state consistent with startup ambient and the revert path. Two tests were updated to reflect the now-correct behaviour: `test_diagnostic_sequence` now expects 20 diagnostic + 4 ambient-restore = 24 state publishes for the 2×2 fixture; `test_diagnostic_uses_correct_brightness_tiers` now excludes the closing ambient-restore frames (identified by the ambient colour) from the D-24 sequence-brightness check, since the ambient restore legitimately uses `led_brightness.ambient`.
**Requires human verification:** The fix intentionally changes diagnostic end-state semantics (restore ambient vs. leave cleared). Confirm this matches the desired operator-facing behaviour. The unified-frame question raised in the review (zero-brightness lit payload vs. retained `b''` delete for the "off" frame) was left as-is; the ambient restore makes the net post-run state correct regardless of that choice.

### WR-01: settings_cache replaced under concurrent reads, leaving in-flight tasks stale

**Files modified:** `src/gruvax/api/admin/settings.py`
**Commit:** 7b54791
**Applied fix:** `update_settings` now mutates the existing `settings_cache` dict in place (`existing.clear(); existing.update(fresh)`) instead of rebinding `app.state.settings_cache` to a new dict. Fire-and-forget tasks (and revert tasks that run 180–900s later) that captured the dict reference at spawn time now observe the new values immediately, satisfying D-15 ("see new LED values immediately"). Falls back to assignment if no dict is present yet.

### WR-02: Retain-mode registry growth bounded only by TTL

**Files modified:** `src/gruvax/mqtt/lifecycle.py`
**Commit:** 2ba3bc5
**Applied fix:** Added a hard cap `_RETAIN_MODE_MAX_HIGHLIGHTS = 64`. In retain mode, before adding a new highlight, `illuminate_with_lifecycle` evicts the oldest entries (insertion-ordered dict) — cancelling each revert task and best-effort reverting its cubes to ambient — until the registry is below the cap. This bounds peak registry size on the constrained Pi/lux host while preserving normal retain-mode UX (default mode is unaffected; the existing cancel-prior path still applies there).
**Requires human verification:** This introduces an eviction algorithm (logic). Tests pass, but confirm the cap value (64) and oldest-first eviction policy match the intended retain-mode behaviour.

### WR-03: No server-side brightness range validation on PUT /settings

**Files modified:** `src/gruvax/api/admin/settings.py`
**Commit:** ec7265e
**Applied fix:** Added a `_BRIGHTNESS_KEYS` set and a fail-fast pre-write validation step that returns HTTP 422 when a brightness key is non-integer or outside `[0, 255]`, mirroring the existing hex-colour validation. The persisted value is now always one the publisher will honour, so the stored value and the published value agree.

### WR-04: `illuminate` `published` field overstates the delivery guarantee

**Files modified:** `src/gruvax/api/illuminate.py`
**Commit:** ac59a8c
**Applied fix:** Documented the response-field semantics explicitly in the endpoint docstring ("scheduled, not delivered") and added an `accepted` field as a clearer alias alongside `published` (kept for backward compatibility; the frontend `illuminateRecord` only checks `res.ok`, so no frontend contract change). Both fields mean "broker connected and fan-out scheduled," never "message delivered."

### WR-05: `publish_ambient` enumeration can raise inside the detached startup task

**Files modified:** `src/gruvax/mqtt/publishers.py`
**Commit:** 05a13fa
**Applied fix:** Wrapped the `gruvax.units` enumeration query in `publish_ambient` in try/except so a DB failure during cube enumeration logs a warning and returns 0 rather than raising inside the detached asyncio task (where, per CR-01, it could otherwise be lost). Mirrors the lifespan startup-step posture.

### WR-06: Illuminate test helper bypasses lifespan, masking the primary lifecycle path

**Files modified:** `tests/unit/test_illuminate_endpoint.py`
**Commit:** 9298cee
**Applied fix:** `_make_app_with_mqtt` now explicitly sets `app.state.highlight_registry = HighlightRegistry()`. Because `ASGITransport` does not run the lifespan, the registry was previously absent and the illuminate endpoint took the registry-None fallback branch. With the registry set, `test_fan_out_count` now exercises the real `illuminate_with_lifecycle` shipping path (confirmed: the never-awaited-coroutine warning changed from `fan_out_illuminate` to `illuminate_with_lifecycle`).

### WR-07: `run_diagnostic` ignores `pool is None` and raises inside the background task

**Files modified:** `src/gruvax/mqtt/publishers.py`
**Commit:** e322a51
**Applied fix:** Added a `pool is None` guard after the `client is None` check in `run_diagnostic`, logging a warning and returning early — mirroring `publish_ambient`. A broker-up / DB-down state no longer raises an uncaught `AttributeError` inside the `BackgroundTask`. (Committed together with WR-09 as both harden the same `run_diagnostic` parameter-reading entry block.)

### WR-09: Diagnostic `inter_cube_ms` read with no bounds or error handling

**Files modified:** `src/gruvax/mqtt/publishers.py`
**Commit:** e322a51
**Applied fix:** Wrapped the `led_diagnostic.inter_cube_ms` read in try/except (defaulting to 200ms on a non-numeric value) and clamped the result to `[0, 2000]` ms, so a hostile or typo'd value can neither raise `ValueError` inside the background task nor make the diagnostic sleep for an arbitrarily long time per cube while holding the `status/#` subscription open. (Committed together with WR-07.)

## Skipped Issues

None — all in-scope findings were fixed.

The five Info findings (IN-01 dead `now_iso`, IN-02 redundant local imports, IN-03 `console.debug` artifact, IN-04 duplicated PIN-length constant, IN-05 ambiguous `duration_ms`) are out of scope for `fix_scope: critical_warning` and were not addressed.

---

_Fixed: 2026-05-24T04:18:56Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_

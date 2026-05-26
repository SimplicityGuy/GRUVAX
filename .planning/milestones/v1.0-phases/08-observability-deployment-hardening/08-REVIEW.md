---
phase: 08-observability-deployment-hardening
reviewed: 2026-05-24T00:00:00Z
depth: standard
files_reviewed: 23
files_reviewed_list:
  - src/gruvax/app.py
  - src/gruvax/logging_config.py
  - src/gruvax/middleware/timing.py
  - src/gruvax/api/version.py
  - src/gruvax/api/health.py
  - src/gruvax/api/search.py
  - src/gruvax/api/locate.py
  - src/gruvax/api/admin/diagnostics.py
  - src/gruvax/api/admin/router.py
  - src/gruvax/db/queries.py
  - migrations/versions/0008_record_stats.py
  - frontend/src/routes/admin/Diagnostics.tsx
  - frontend/src/routes/admin/Diagnostics.css
  - frontend/src/routes/admin/AdminShell.tsx
  - frontend/src/api/adminClient.ts
  - frontend/src/App.tsx
  - frontend/src/routes/kiosk/StalenessBar.tsx
  - frontend/src/routes/kiosk/StalenessBar.css
  - frontend/src/routes/kiosk/KioskView.tsx
  - Dockerfile
  - compose.yaml
  - .github/workflows/ci.yml
  - scripts/check_benchmark.py
findings:
  critical: 1
  warning: 4
  info: 3
  total: 8
status: issues_found
---

# Phase 8: Code Review Report

**Reviewed:** 2026-05-24
**Depth:** standard
**Files Reviewed:** 23
**Status:** issues_found

## Summary

Phase 8 adds structured-JSON logging, a log ring buffer, slow-query recording, sync-staleness tracking, durable `record_stats` counters, the admin diagnostics page, the kiosk staleness banner, and deployment hardening (Dockerfile multi-stage build, CI Alembic round-trip, benchmark SLO gate).

The privacy-sensitive counter increment path is clean: `release_id` only, no query text stored. SQL is fully parameterized throughout. Admin gating on the diagnostics endpoints is correctly wired through `require_admin`. The `el()`/`replaceChildren()` pattern for the log terminal is correct with no `innerHTML` usage. The Dockerfile uses only `ARG` (not `ENV`) for build-time metadata so secrets cannot be baked into layers by accident.

Three issues need attention before ship: a subtle broken-reference bug in the background-task strong-reference pattern that silently defeats the GC-cancellation guard in `search.py` and `locate.py` (BLOCKER), the SLO-gate script checking `mean` while the docstring and CI comment advertise `p95` (BLOCKER in terms of contract accuracy — it will miss high-tail latency), and hardcoded RGBA hex color values in `Diagnostics.css` that violate the project's "consume tokens; never hardcode hex" design contract.

---

## Critical Issues

### CR-01: Background-task strong-reference guard silently broken in search.py and locate.py

**File:** `src/gruvax/api/search.py:72` and `src/gruvax/api/locate.py:122`

**Issue:** Both handlers use `getattr(request.app.state, "background_tasks", set())` to obtain the strong-reference set. The fallback default `set()` creates a **new, anonymous, immediately-discarded `set` object** — it is not stored anywhere. When `app.state.background_tasks` is absent (e.g. early in startup before lifespan completes, or in a test that bypasses lifespan), `bg.add(task)` adds the task to a throw-away set that is garbage-collected the moment the handler returns. The task loses its only strong reference and is eligible for GC cancellation mid-flight — exactly the failure mode the code comment says it is preventing.

`app.state.background_tasks` is correctly initialized to a real `set` in `lifespan` (app.py line 203), so in normal production operation this code path is safe. However:
1. Tests that construct the app without running lifespan have no protection.
2. Any request that somehow runs before the lifespan yield (impossible in current FastAPI but a footgun if the dependency changes) silently drops the guard.
3. The comment "CR-01: strong-reference via app.state.background_tasks" implies correctness that is conditional on `background_tasks` being present.

The real fix is to never fall back to a new `set()`. If the attribute is absent, either raise (fail fast in tests) or use a module-level sentinel set rather than a silent throw-away default.

**Fix:**
```python
# In search.py and locate.py — replace the getattr fallback pattern:

# BEFORE (broken fallback):
bg: set[asyncio.Task[None]] = getattr(request.app.state, "background_tasks", set())

# AFTER (fail-fast if not initialized):
bg: set[asyncio.Task[None]] = request.app.state.background_tasks
# Or, for graceful degradation without silent guard defeat:
bg: set[asyncio.Task[None]] | None = getattr(request.app.state, "background_tasks", None)
if bg is not None:
    bg.add(task)
    task.add_done_callback(bg.discard)
```

---

## Warnings

### WR-01: Benchmark SLO gate checks mean, not p95 — docstring and CI comment misrepresent the gate

**File:** `scripts/check_benchmark.py:1-11` and `.github/workflows/ci.yml:13`

**Issue:** The module docstring says "search p95 <= 200 ms, locate p95 <= 50 ms" and the CI comment reads "search p95 <= 200 ms, locate p95 <= 50 ms on synthetic data". The script actually reads `stats["mean"]` (line 64) and compares against the budget, not the 95th-percentile value. `pytest-benchmark` JSON also provides `stats["ops"]`, `stats["min"]`, `stats["max"]`, `stats["median"]`, `stats["stddev"]`, `stats["irs_mean"]`, and `stats["percentile_95"]` (or `hdr_min`/`hdr_max` depending on the plugin version). The p95 key name varies: `"percentile_95"` in older plugin versions; `"ops"` is never the right field.

Checking mean is weaker than checking p95: a tail spike that affects 5% of requests would pass mean while failing a proper p95 gate. For a kiosk that must respond within ~200 ms "perceived from keystroke", p95 is the more meaningful SLO. The current gate will pass even when 5% of requests breach the SLO.

**Fix:**
```python
# scripts/check_benchmark.py — replace mean check with p95:
stats = bench.get("stats", {})
# pytest-benchmark stores p95 as "percentile_95" (seconds)
p95_s: float = stats.get("percentile_95", float("inf"))
p95_ms = p95_s * 1000.0
# Update the comparison variable and messages accordingly
```
Update the docstring and CI comment to match whichever metric is actually checked.

---

### WR-02: Recent-logs ring buffer exposes arbitrary application log messages to the admin UI without filtering

**File:** `src/gruvax/api/admin/diagnostics.py:65-68` and `src/gruvax/logging_config.py:77-88`

**Issue:** `LogRingHandler.emit()` captures the full `record.getMessage()` string for every log record at DEBUG level and above. The `msg` field is the **formatted** log message — it includes whatever was passed to `logger.info(...)`, `logger.warning(...)`, etc., across every module in the codebase (including third-party libraries that log at WARNING).

The diagnostics endpoint serves the last 20 entries to any authenticated admin user. The CLAUDE.md security note says "Body excludes: session_secret, database_url, pin, raw query text." If any log call — in current code or future code — inadvertently includes a DSN, PIN, or query string in its `%s` argument (e.g., a psycopg connection error that stringifies the DSN, a validator that logs the input before rejecting it), it would be captured in the ring and served verbatim to the browser.

The current code has no filtering rule on the ring: the `LogRingHandler` has `level=logging.DEBUG` and captures all loggers (root handler). There is no allowlist of logger names and no scrub of message content.

This is a defence-in-depth gap, not an immediate confirmed leak, but the architectural choice (capture everything, filter nothing, serve to UI) is fragile.

**Fix:** Either:
(a) Set the `LogRingHandler` level to `logging.INFO` and add a logger-name allowlist limited to `gruvax.*` to exclude third-party log messages that could embed connection details:
```python
ALLOWED_LOGGER_PREFIXES = ("gruvax.",)

def emit(self, record: logging.LogRecord) -> None:
    if not any(record.name.startswith(p) for p in ALLOWED_LOGGER_PREFIXES):
        return
    ...
```
(b) Or set `level=logging.INFO` (not DEBUG) as the ring handler level so debug-level messages that might be more verbose are excluded.

---

### WR-03: `stalenessStatus` returns `'ok'` when `sync_age_seconds` is `null`/`undefined` — kiosk banner suppressed during health outage

**File:** `frontend/src/routes/admin/Diagnostics.tsx:36-40`

**Issue:** `stalenessStatus` returns `'ok'` when `seconds` is `null` or `undefined`. This is intentional for the kiosk (`StalenessBar` hides itself when age is unknown, which is the correct UX). However, in the admin `StalenessSection`, the same `stalenessStatus` function drives the badge shown on the diagnostics page. When the sync-age query returns `null` (v_collection empty, or background refresh not yet completed), the admin badge shows `OK` even though the actual staleness is unknown.

An `ok` badge for an unknown sync state is misleading to the operator. The admin page should distinguish `null` from "genuinely fresh".

**Fix:**
```typescript
// Add a 4th state to the admin diagnostics staleness function:
function stalenessStatus(seconds: number | null): 'ok' | 'stale' | 'outdated' | 'unknown' {
  if (seconds === null || seconds === undefined) return 'unknown'
  if (seconds > 14 * 86400) return 'outdated'
  if (seconds > 3 * 86400) return 'stale'
  return 'ok'
}
// Then add a corresponding .diag-badge--unknown CSS class and render "UNKNOWN" text.
```

---

### WR-04: Hardcoded RGBA hex values in Diagnostics.css violate the design token contract

**File:** `frontend/src/routes/admin/Diagnostics.css:125` and `frontend/src/routes/admin/Diagnostics.css:282`

**Issue:** Two rules use raw `rgba()` with hardcoded hex-derived values:
- Line 125: `background: rgba(26, 122, 74, 0.12)` — described as `--gruvax-success tint`
- Line 282: `background: rgba(192, 57, 43, 0.06)` — described as `--gruvax-error tint`

CLAUDE.md design language section states: "Consume tokens; never hardcode hex." The comment "token-safe via rgba" does not make the values token-safe — they remain magic numbers derived from the token color values. If `--gruvax-success` or `--gruvax-error` ever change, these hover/tint states will silently diverge.

**Fix:** Use `color-mix()` against the token:
```css
/* Line 125 */
background: color-mix(in srgb, var(--gruvax-success) 12%, transparent);

/* Line 282 */
background: color-mix(in srgb, var(--gruvax-error) 6%, transparent);
```
`color-mix(in srgb, ...)` with `transparent` is supported in all modern browsers (Chromium 111+, which covers the kiosk Chromium target).

---

## Info

### IN-01: `check_benchmark.py` silently does not fail when known benchmarks are missing from the JSON

**File:** `scripts/check_benchmark.py:78-86`

**Issue:** When neither `test_search_slo_benchmark` nor `test_locate_benchmark` appears in the benchmark JSON (e.g. test IDs drift after a rename), the script prints a WARNING to stderr but exits 0 (`passed` remains `True` because the loop body never executes). The CI step therefore passes even though no SLO checks were performed. The code comment acknowledges this ("warn but don't fail") but the rationale ("the test itself will fail if the benchmark didn't run at all") only holds when `--benchmark-only` causes pytest to exit non-zero for missing tests — which it does not; `--benchmark-only` simply skips non-benchmark tests.

**Fix:** Exit 1 (or at minimum exit 2 with a "no benchmarks checked" warning) when `checked == 0`:
```python
if checked == 0:
    print("WARNING: ...", file=sys.stderr)
    # Return False so CI fails and the operator notices the gate is not running:
    return False
```

---

### IN-02: `console.debug` left in production `adminClient.ts`

**File:** `frontend/src/api/adminClient.ts:352`

**Issue:** `console.debug('[gruvax] signalEditing network error (non-fatal):', err)` is intentional for diagnostics. However, in a production Chromium kiosk, the DevTools console is not normally open, so this is harmless in practice. It is still a debug artifact in shipped code and `err` may contain a `TypeError` with a URL or request detail that shows up in remote DevTools sessions.

**Fix:** Either remove the `console.debug` or gate it on `import.meta.env.DEV`:
```typescript
if (import.meta.env.DEV) {
  console.debug('[gruvax] signalEditing network error (non-fatal):', err)
}
```

---

### IN-03: `formatSyncAge` returns `'< 1h ago'` for any age between 0 and 3600 seconds — including 0

**File:** `frontend/src/routes/admin/Diagnostics.tsx:28-33`

**Issue:** `formatSyncAge` returns `'< 1h ago'` for any value less than 3600 seconds, including 0 (synced right now) and very small values (2 seconds ago). The string is misleading for a fresh sync: "< 1h ago" when `sync_age_seconds = 5` is technically correct but poor UX — "just now" or "< 1 min ago" would be more informative.

This is a UX-only issue with no correctness or security impact.

**Fix:**
```typescript
function formatSyncAge(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return '—'
  if (seconds < 60) return 'just now'
  if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60)
    return `${minutes} min ago`
  }
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  if (days === 0) return `${hours}h ago`
  if (hours === 0) return `${days}d ago`
  return `${days}d ${hours}h ago`
}
```

---

_Reviewed: 2026-05-24_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

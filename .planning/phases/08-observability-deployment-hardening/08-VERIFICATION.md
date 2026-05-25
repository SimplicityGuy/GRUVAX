---
phase: 08-observability-deployment-hardening
verified: 2026-05-24T22:00:00Z
status: human_needed
score: 12/12 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Open /admin/diagnostics in a running stack and confirm all 5 section cards render per UI-SPEC"
    expected: "SYNC STATUS, TOP SEARCHED (with inline RESET STATS confirm), SLOW QUERIES, SYSTEM (MQTT/pool/phantom), RECENT LOGS all render with Nordic Grid styling; Refresh reloads data; no continuous polling; reset flow works"
    why_human: "UI layout, typography (24/18/16/14px only, Barlow ALL-CAPS headings, DM Mono numbers), dark logs terminal, inline confirm flow — cannot be asserted by grep"
  - test: "Force sync_age_seconds > 14d on kiosk and verify staleness banner"
    expected: "Yellow banner appears ABOVE the grid with copy 'Collection data may be outdated — last synced {N}d ago'; search still works; no-results page has NO staleness hint; banner disappears when sync is recent"
    why_human: "Requires forcing a stale state in the dev DB or stub, then checking visual placement, color, copy, icon, and dismiss-absence in a browser"
gaps: []
deferred: []
---

# Phase 8: Observability + Deployment Hardening — Verification Report

**Phase Goal:** `/api/health` reports per-subsystem reachability, the slow-query log proves the 200 ms search SLO, sync staleness is surfaced to admin (and kiosk if stale > 14 days, per D-01), Compose services declare log limits + healthchecks, and a `/api/version` endpoint reports the running build — the v1 is operable, observable, and self-healing.
**Verified:** 2026-05-24T22:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `GET /api/health` returns per-subsystem reachability (`db`, `discogsography_view_check`, `mqtt`), `version` (real git SHA), `started_at`, `sync_age_seconds` | ✓ VERIFIED | `src/gruvax/api/health.py` reads all fields from `app.state`; `version` is `GIT_SHA` from `gruvax._version` (not hardcoded "0.1.0") |
| 2 | `GET /api/version` returns `git_sha`, `build_timestamp`, `environment` | ✓ VERIFIED | `src/gruvax/api/version.py` imports from `gruvax._version`; `app.py` registers the router at `/api` prefix |
| 3 | Application logs emit structured JSON; LOG_LEVEL is env-configurable; in-memory log ring captures `gruvax.*` logs at INFO+ only (WR-02 fix) | ✓ VERIFIED | `logging_config.py` has `JsonFormatter` + `LogRingHandler`; `app.py` lifespan attaches `LogRingHandler` to `logging.getLogger("gruvax")` at INFO, not root; root gets JSON stream handler |
| 4 | Slow-query ring records request-total AND db_ms; `/api/search` flagged at >200ms, `/api/locate` at >50ms | ✓ VERIFIED | `middleware/timing.py` `SLO_THRESHOLDS_MS = {"/api/search": 200.0, "/api/locate": 50.0}`; both `search.py` and `locate.py` call `record_slow_query()` after measuring timing |
| 5 | `sync_age_seconds` is refreshed from `max(v_collection.synced_at)` in a background task without a per-request DB hit | ✓ VERIFIED | `app.py` lifespan creates `_refresh_sync_age()` coroutine that runs `SELECT EXTRACT(EPOCH FROM (now() - max(synced_at))) FROM gruvax.v_collection` every 60s and writes to `app.state.sync_age_seconds` |
| 6 | Admin diagnostics page exposes all 7 SC#2 rows (staleness, top-N, slow queries, MQTT, pool, phantom count, recent logs); gated by admin session + CSRF | ✓ VERIFIED | `api/admin/diagnostics.py` `GET /diagnostics` requires `Depends(require_admin)`; returns all 7 fields; registered in `api/admin/router.py`; `Diagnostics.tsx` calls `getDiagnostics()` in `useEffect` + Refresh |
| 7 | Admin staleness thresholds: yellow >3d, red >14d (D-01) | ✓ VERIFIED | `Diagnostics.tsx` `stalenessStatus()`: `seconds > 14*86400` → `'outdated'`, `seconds > 3*86400` → `'stale'` |
| 8 | Kiosk shows staleness banner at >14d from `/api/health` (D-01/D-02); no-results stays generic | ✓ VERIFIED | `StalenessBar.tsx` `STALE_THRESHOLD_SECONDS = 14*24*60*60`; `KioskView.tsx` fetches `/api/health` via `useQuery` and passes `sync_age_seconds` to `<StalenessBar>`; no staleness hint added to no-results path |
| 9 | OBS-07 PRIVACY: `record_stats` table has NO `query_text` column; only `release_id`-keyed counters | ✓ VERIFIED | Migration 0008 CREATE TABLE shows `release_id`, `search_count`, `search_count_7d`, `selection_count`, `selection_count_7d`, timestamps — no text column; `increment_search_count` and `increment_selection_count` accept only `release_id: int` |
| 10 | CI proves Alembic round-trip (`upgrade head → downgrade base → upgrade head`) on every push | ✓ VERIFIED | `.github/workflows/ci.yml` Step "Alembic round-trip" runs all three commands as hard-fail (no `continue-on-error`) |
| 11 | CI benchmark SLO gate checks p95 `/api/search` ≤200ms and p95 `/api/locate` ≤50ms on synthetic data only | ✓ VERIFIED | `scripts/check_benchmark.py` uses `_p95_ms()` (nearest-rank 95th-percentile from raw samples, falls back to mean with loud warning); CI seeds only `fixtures/synth_collection.sql`; gate is hard-fail |
| 12 | Compose declares `logging:` max-size + max-file on `api` and `mosquitto`; all non-debug services have `healthcheck:` + `restart: unless-stopped` | ✓ VERIFIED | `compose.yaml`: `api` (lines 91-95), `gruvax-dev-pg` (lines 127-131), `mosquitto` (lines 154-158) all have `logging: driver: json-file, max-size: 10m, max-file: 3`; all three have `healthcheck:` and `restart: unless-stopped` |

**Score:** 12/12 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/gruvax/api/health.py` | Enriched /api/health with git SHA + sync_age_seconds | ✓ VERIFIED | Returns all OBS-01 fields; reads GIT_SHA from `_version` module |
| `src/gruvax/api/version.py` | GET /api/version with git_sha/build_timestamp/environment | ✓ VERIFIED | Three-field JSON, registered at `/api/version` |
| `src/gruvax/logging_config.py` | JsonFormatter + LogRingHandler | ✓ VERIFIED | Both classes present; LogRingHandler defaults to INFO level |
| `src/gruvax/middleware/timing.py` | SLO_THRESHOLDS_MS + record_slow_query helper | ✓ VERIFIED | Thresholds 200ms/50ms; helper reads ring from `app.state.slow_query_ring` |
| `src/gruvax/_version.py` | GIT_SHA, BUILD_TIMESTAMP, ENVIRONMENT | ✓ VERIFIED | File exists with real SHA `b79036b`; Dockerfile bakes at build time via ARG |
| `migrations/versions/0008_record_stats.py` | gruvax.record_stats table (release_id-keyed, no query text) | ✓ VERIFIED | Table has BIGINT release_id PRIMARY KEY + counters + timestamps; upgrade/downgrade both present |
| `src/gruvax/api/admin/diagnostics.py` | Admin-gated GET + reset-stats POST | ✓ VERIFIED | Both endpoints require `Depends(require_admin)`; returns 7 SC#2 rows |
| `frontend/src/routes/admin/Diagnostics.tsx` | /admin/diagnostics page (7 sections) | ✓ VERIFIED | 542 lines; all 5 visual sections (Staleness, TopSearched, SlowQuery, SystemStatus, RecentLogs) with el()/replaceChildren() for log terminal — no innerHTML |
| `frontend/src/routes/kiosk/StalenessBar.tsx` | Kiosk staleness banner (>14d) | ✓ VERIFIED | `STALE_THRESHOLD_SECONDS = 14*24*60*60`; returns null below threshold; role="alert" |
| `.github/workflows/ci.yml` | GitHub Actions with Alembic round-trip + benchmark SLO gate | ✓ VERIFIED | Synthetic-only seed; round-trip hard-fail; benchmark p95 gate hard-fail |
| `scripts/check_benchmark.py` | p95 SLO gate script | ✓ VERIFIED | `_p95_ms()` computes nearest-rank 95th percentile from raw samples |
| `compose.yaml` | log limits + healthchecks on all production services | ✓ VERIFIED | Three services with `logging:` max-size + `healthcheck:` + `restart: unless-stopped` |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `app.py lifespan` | `logging_config.py` | `JsonFormatter` on root + `LogRingHandler` on `gruvax` logger | ✓ WIRED | Lines 88-100; WR-02 fix applied |
| `app.py lifespan` | `app.state.slow_query_ring` | `deque(maxlen=50)` at lifespan startup | ✓ WIRED | Line 111 |
| `app.py lifespan` | `gruvax.v_collection.synced_at` | `_refresh_sync_age()` background task, 60s cadence | ✓ WIRED | Lines 214-234; task kept in `app.state.background_tasks` (CR-01 fix) |
| `search.py` | `increment_search_count` | `asyncio.create_task` on top result `release_id` | ✓ WIRED | Lines 71-90; privacy: only int passed |
| `locate.py` | `increment_selection_count` | `asyncio.create_task` on successful locate `release_id` | ✓ WIRED | Lines 121-141; privacy: only int passed |
| `search.py` | `record_slow_query` | After DB roundtrip; total_ms = db_ms for search | ✓ WIRED | Line 64 |
| `locate.py` | `record_slow_query` | After CPU estimate; db_ms=0.0 | ✓ WIRED | Line 145 |
| `health.py` | `gruvax._version.GIT_SHA` | `from gruvax._version import GIT_SHA` with ImportError fallback | ✓ WIRED | Lines 22-25; fallback = "dev" for non-Docker runs |
| `KioskView.tsx` | `StalenessBar` | `useQuery('/api/health')` → `syncAgeSeconds` prop | ✓ WIRED | Line 457 |
| `App.tsx` | `Diagnostics` route | `<Route path="diagnostics" element={<Diagnostics />} />` | ✓ WIRED | Line 58 |
| `adminClient.ts` | `/api/admin/diagnostics` | `getDiagnostics()` called in `useEffect` + Refresh handler | ✓ WIRED | Lines 631-638 |
| `ci.yml` | `fixtures/synth_collection.sql` | `psql ... < fixtures/synth_collection.sql` (synthetic only) | ✓ WIRED | No real CSV reference in any step |
| `compose.yaml api` | `json-file` log driver | `logging.driver: json-file, max-size: 10m` | ✓ WIRED | Lines 91-95 |
| `compose.yaml mosquitto` | `json-file` log driver | `logging.driver: json-file, max-size: 10m` | ✓ WIRED | Lines 154-158 |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `health.py` | `sync_age_seconds` | `app.state.sync_age_seconds` ← `_refresh_sync_age()` ← `gruvax.v_collection.synced_at` | Yes — DB query every 60s | ✓ FLOWING |
| `health.py` | `version` | `GIT_SHA` ← `_version.py` ← Dockerfile ARG / `just build-version` | Yes — baked at Docker build time | ✓ FLOWING |
| `diagnostics.py` | `top_searched` | `get_top_searched(pool)` ← `gruvax.record_stats JOIN gruvax.v_collection` | Yes — live DB query | ✓ FLOWING |
| `diagnostics.py` | `slow_queries` | `app.state.slow_query_ring` ← `record_slow_query()` in handlers | Yes — populated by every slow request | ✓ FLOWING |
| `diagnostics.py` | `recent_logs` | `app.state.log_ring_buffer` ← `LogRingHandler` on `gruvax.*` logger | Yes — captures gruvax.* INFO+ logs | ✓ FLOWING |
| `StalenessBar.tsx` | `syncAgeSeconds` | `healthData.sync_age_seconds` ← `useQuery('/api/health')` ← `app.state.sync_age_seconds` | Yes — refreshed every 60s | ✓ FLOWING |
| `Diagnostics.tsx` | `data.sync_age_seconds` | `getDiagnostics()` ← `GET /api/admin/diagnostics` ← `app.state.sync_age_seconds` | Yes — falls back to live DB query if cache empty | ✓ FLOWING |

---

### Behavioral Spot-Checks

Step 7b SKIPPED — no running server available for live endpoint checks. Code-level verification is complete; behavioral assertion requires a running stack (covered by `just demo` and human verification steps).

---

### Probe Execution

Step 7c SKIPPED — no `scripts/*/tests/probe-*.sh` files exist in this phase. The CI Alembic round-trip serves as the probe equivalent.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| OBS-01 | 08-01, 08-03 | /api/health per-subsystem reachability + version + started-at | ✓ SATISFIED | `health.py` returns all fields; `GIT_SHA` replaces hardcoded "0.1.0" |
| OBS-02 | 08-01 | Structured JSON logs; LOG_LEVEL env-configurable | ✓ SATISFIED | `logging_config.py` `JsonFormatter`; `settings.LOG_LEVEL` → `_log_level`; ring scoped to `gruvax.*` |
| OBS-03 | 08-06 | Alembic round-trip in CI on every push | ✓ SATISFIED | `ci.yml` hard-fail `upgrade head → downgrade base → upgrade head` |
| OBS-04 | 08-01, 08-03 | /api/version with git SHA, build timestamp, environment | ✓ SATISFIED | `version.py` + `_version.py` + Dockerfile ARG injection |
| OBS-05 | 08-01, 08-03, 08-04 | Slow-query log; search >200ms, locate >50ms flagged | ✓ SATISFIED | `timing.py` thresholds; hooks in `search.py` and `locate.py`; surfaced in diagnostics page |
| OBS-06 | 08-01, 08-03, 08-04, 08-05 | Sync staleness surfaced to admin (3d/14d) and kiosk (14d) | ✓ SATISFIED | Background refresh task; health endpoint; diagnostics page; StalenessBar |
| OBS-07 | 08-02, 08-03, 08-04 | Top-N most-searched; NO per-query text persisted | ✓ SATISFIED | `record_stats` has no `query_text` column; only `release_id` int passed to increment functions |
| DEP-04 | 08-06 | Compose logging: max-size + max-file on gruvax-api + mosquitto | ✓ SATISFIED | Both services + gruvax-dev-pg have `logging: json-file, max-size: 10m, max-file: 3` |
| DEP-05 | 08-06 | Compose healthchecks + restart: unless-stopped | ✓ SATISFIED | All three non-debug services verified intact |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `frontend/src/routes/admin/Diagnostics.tsx` | 37 | `stalenessStatus()` returns `'ok'` when `seconds === null` | ⚠️ Warning | Admin badge shows "OK" when sync state is actually unknown (null) — misleading to operator; WR-03 from code review; not fixed |
| `scripts/check_benchmark.py` | 92-101 | `checked == 0` returns `passed=True` → exits 0 | ℹ️ Info | If benchmark test IDs drift, CI silently passes with no SLO check; IN-01 from code review; not fixed |
| `frontend/src/api/adminClient.ts` | 352 | `console.debug(...)` in production path | ℹ️ Info | Debug artifact in shipped code; IN-02 from code review; not fixed |
| `frontend/src/routes/admin/Diagnostics.tsx` | 28-33 | `formatSyncAge()` returns `'< 1h ago'` for 0 seconds | ℹ️ Info | Misleading for freshly-synced collections; IN-03 from code review; not fixed |

**No `TBD`, `FIXME`, or `XXX` markers found in any Phase 8 files.**

---

### Code Review Findings Applied

Four code-review blockers/warnings were fixed in commit `2354c7e`:

- **CR-01 (BLOCKER → FIXED):** Background-task strong-reference guard in `search.py` and `locate.py` — both now use `getattr(..., None)` + create-and-persist pattern instead of silent throwaway `set()` fallback.
- **WR-01 (WARNING → FIXED):** `check_benchmark.py` now computes true p95 via `_p95_ms()` (nearest-rank 95th-percentile from raw samples), not mean.
- **WR-02 (WARNING → FIXED):** Log ring handler now attached to `logging.getLogger("gruvax")` at INFO level only — third-party logs cannot reach admin UI.
- **WR-04 (WARNING → FIXED):** `Diagnostics.css` hardcoded RGBA values replaced with `color-mix(in srgb, var(--gruvax-success) 12%, transparent)` and `color-mix(in srgb, var(--gruvax-error) 6%, transparent)`.

Four items from the code review remain unfixed (WR-03, IN-01, IN-02, IN-03). WR-03 is a WARNING; the three IN-* items are INFO. None constitute BLOCKER-level failures for the phase goal.

---

### Human Verification Required

#### 1. Admin Diagnostics Page Visual Rendering

**Test:**
1. `docker compose up -d --build api` (dev PIN = 0000)
2. Open `/admin/diagnostics` on a phone-width viewport after signing in
3. Run a few kiosk searches first so TOP SEARCHED and RECENT LOGS have data
4. Confirm all 5 section cards render with Nordic Grid styling: blue Barlow Condensed headings (24px ALL-CAPS), Space Grotesk 14px body, DM Mono numbers
5. Tap REFRESH — data reloads; "Last refreshed" updates; network tab shows no continuous polling
6. Tap RESET STATS → CONFIRM RESET? appears inline → tap KEEP STATS (no change) → then RESET STATS → YES, RESET → "Stats cleared." appears and TOP SEARCHED empties

**Expected:** All 5 sections visible and styled per Nordic Grid; REFRESH only fires on open + button tap; reset flow works end-to-end

**Why human:** UI layout, font sizes (exactly 24/18/16/14px), Barlow label styling, dark terminal appearance, inline confirm state transitions — not verifiable by grep or static analysis

---

#### 2. Kiosk Staleness Banner Visual Rendering and Threshold Behavior

**Test:**
1. `docker compose up -d --build api`
2. Force stale state: set `max(v_collection.synced_at)` > 14 days ago in the dev DB, then wait up to 60s for the health query to refetch (or reload the kiosk)
3. Open the kiosk URL in Chromium (or phone-width browser)
4. Confirm: yellow banner appears ABOVE the grid (not overlaying it) with copy "Collection data may be outdated — last synced {N}d ago", Space Grotesk 18px, blue-darker text, warning triangle icon, no dismiss button
5. Run a search — confirm search still works fully
6. Search a nonsense term — confirm the no-results page is GENERIC with NO staleness hint (D-02)
7. Restore sync timestamp to recent; reload — confirm banner disappears

**Expected:** Banner appears only when stale >14d; search unaffected; no-results stays generic; banner gone when fresh

**Why human:** Requires forcing stale state in dev DB; visual placement verification above vs. overlaying grid; color/font/icon appearance; D-02 no-results page behavior check — cannot be asserted statically

---

### WR-03 Unfixed Warning Note

`stalenessStatus()` in `Diagnostics.tsx` (line 37) returns `'ok'` when `seconds === null`. The admin badge will show "OK" even when `sync_age_seconds` is null (e.g., v_collection is empty or the background task has not yet completed its first run). The recommended fix (add an `'unknown'` state with a corresponding `.diag-badge--unknown` CSS class) was called out in WR-03 of the code review but was not applied.

This is a WARNING, not a BLOCKER: the Core Value flow and all automated gates pass; only the admin diagnostics page shows a potentially misleading staleness badge in the edge case of a null sync_age.

---

### Gaps Summary

No automated-check gaps found. All 12 must-have truths verify against the actual codebase. The four unfixed code-review items (WR-03, IN-01, IN-02, IN-03) are classified as WARNING or INFO and do not constitute BLOCKER-level gaps against the phase goal.

The two outstanding items both require human browser-based verification (auto-approved checkpoint tasks from `08-04-PLAN.md` and `08-05-PLAN.md`). Until those are human-confirmed, the status is `human_needed`.

---

_Verified: 2026-05-24T22:00:00Z_
_Verifier: Claude (gsd-verifier)_

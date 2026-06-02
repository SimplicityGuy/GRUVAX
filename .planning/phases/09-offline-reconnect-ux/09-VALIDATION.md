---
phase: 09
slug: offline-reconnect-ux
status: reconstructed
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-02
reconstructed_from: [09-01-SUMMARY, 09-02-SUMMARY, 09-03-SUMMARY, 09-04-SUMMARY, 09-05-SUMMARY, 09-VERIFICATION]
---

# Phase 9 — Validation Strategy

> Reconstructed post-execution from phase artifacts (State B). Audits Nyquist
> verification coverage for OFF-01..OFF-04 and fills the one MISSING automated gap
> (OFF-03 backend SSE `retry:` jitter).

---

## Test Infrastructure

Phase 9 spans two test stacks (frontend kiosk UX + backend SSE):

| Property | Frontend | Backend |
|----------|----------|---------|
| **Framework** | vitest 4.x (jsdom) | pytest + pytest-asyncio |
| **Config file** | `frontend/vite.config.ts` | `pyproject.toml` |
| **Quick run command** | `npm --prefix frontend test` | `uv run pytest tests/integration/test_sse_per_profile.py -q` |
| **Full suite command** | `npm --prefix frontend test` (`vitest run`) | `uv run pytest tests -q` |
| **Estimated runtime** | ~15 s (130 tests) | ~20 s (SSE live-server fixture spins a uvicorn thread) |

---

## Sampling Rate

- **After every task commit:** Run the relevant stack's quick command.
- **After every plan wave:** Run that stack's full suite.
- **Before `/gsd:verify-work`:** Both suites must be green.
- **Max feedback latency:** ~20 s.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 1 | OFF-03 (backend) | T-09-03 (retry value client-readable — accepted) | Initial SSE frame emits `retry:` in [2000,8000] ms; no reconnect storm | integration | `uv run pytest tests/integration/test_sse_per_profile.py -k retry -q` | ✅ | ✅ green |
| 09-02-01 | 02 | 1 | OFF-01 | — | `setSseConnected(false)`→`bannerVisible=true`; `(true)`→`false`; `lastSeenAt` preserved on disconnect | unit | `npm --prefix frontend test -- store.connectivity` | ✅ | ✅ green |
| 09-02-02 | 02 | 1 | OFF-03 (frontend) | T-09-09 | `QueryClient networkMode:'always'` prevents `navigator.onLine` refetch pause/storm | unit (config assert) | `npm --prefix frontend test -- store.connectivity` | ✅ | ✅ green |
| 09-03-01 | 03 | 2 | OFF-01 | T-09-09 (navigator.onLine masking) | Banner renders on `!sseConnected` only; `onLine` selects copy text; `role=alert`, not dismissible | unit | `npm --prefix frontend test -- OfflineBanner` | ✅ | ✅ green |
| 09-03-02 | 03 | 2 | OFF-02 | T-09-07 (client gating = UX only) | `isOffline` disables + de-focuses search input, swaps placeholder; locate result/highlight preserved | unit | `npm --prefix frontend test -- SearchBox` | ✅ | ✅ green |
| 09-03-03 | 03 | 2 | OFF-01/02/04 | T-09-08 (device_revoked masked by banner) | onerror→banner+disabled search; onopen-after-onerror→banner clears+toast; device_revoked still fires `triggerRevoke()` | unit | `npm --prefix frontend test -- KioskView.EventSource` | ✅ | ✅ green |
| 09-04-01 | 04 | 3 | OFF-04 | T-09-10 (dismissed diff badge) | `resync()` invalidates `['search']` + `['units']` + `['cubes']` on onopen/server_hello | unit | `npm --prefix frontend test -- KioskView.EventSource` | ✅ | ✅ green |
| 09-04-02 | 04 | 3 | OFF-04 | — | WR-02: `setShowBackOnlineToast(false)` in onerror + server_shutdown → no dual-banner state | unit | `npm --prefix frontend test -- KioskView.EventSource` | ✅ | ✅ green |
| 09-05-01 | 05 | 4 | OFF-01 | T-09-08 | `everConnected` one-way latch; `bannerVisible = !sseConnected && everConnected` → no banner on bootstrap/403 device_unknown | unit | `npm --prefix frontend test -- store.connectivity OfflineBanner` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure (vitest + pytest live-server SSE harness) covered all phase requirements. No framework install needed.

One MISSING automated gap was found during reconstruction and filled:

- [x] `tests/integration/test_sse_per_profile.py::test_sse_emits_jittered_retry` — OFF-03 backend `retry:` jitter range assertion (reuses the existing bound-cookie `live_server` fixture; never modifies `events.py`).

---

## Manual-Only Verifications

These are timing- and visually-bound: they require process-level start/stop of `gruvax-api` and a running kiosk browser, so they cannot be asserted by unit/integration tests. The *logic* behind each is automated above; only the real-world timing/appearance is human-confirmed. Carried from `09-VERIFICATION.md`.

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Offline banner appears within one SSE ping interval (~15–20 s) of API stop | OFF-01 / SC1 | Requires live process control + browser observation; the ~15 s window depends on `ping=15` keepalive + browser retry timing | Stop `gruvax-api` with a prior locate result loaded; confirm blue reversed-palette banner within ~15 s. Toggle DevTools offline with API up → NO banner (SSE-authoritative, not `navigator.onLine`). |
| Degraded-mode visual state | OFF-02 / SC2 | Layout, input focus state, and visual appearance need a running browser | While offline: shelf grid + highlight remain; search greyed/non-focusable with "Search unavailable while offline"; profile-switch absent; cube taps inert. |
| Banner clears within 30 s of API restart + "Back online" toast | OFF-04 / SC3 | Live process restart + real timing observation; jitter spreads reconnect over 2–8 s | Restart `gruvax-api`; confirm banner clears within 30 s, SyncToast shows "Back online" and auto-dismisses (~4 s), search re-enables. |
| Stale search refreshed after >30 s outage | OFF-04 / SC4 | Requires a real outage window + observing fresh results post-reconnect | After >30 s offline + reconnect, confirm `resync()` flushed `['search']` so results are fresh (active invalidation, per 09-04 user decision superseding D-73/74). |
| WR-01: "Back online" toast auto-dismisses under background-refetch load | OFF-04 (advisory) | Timing observation with concurrent health/session polling | Trigger reconnect while background queries fire; confirm toast dismisses in ~4 s (stable `useCallback` onDismiss). |

---

## Validation Sign-Off

- [x] All tasks have automated verify or are documented manual-only
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (OFF-03 jitter test added)
- [x] No watch-mode flags (`vitest run`, not `vitest`)
- [x] Feedback latency < 20 s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-02

---

## Validation Audit 2026-06-02

| Metric | Count |
|--------|-------|
| Requirements audited | 4 (OFF-01..OFF-04) |
| Gaps found | 1 (OFF-03 backend SSE retry jitter — MISSING) |
| Resolved (automated) | 1 |
| Escalated | 0 |
| Manual-only (timing/visual) | 5 |

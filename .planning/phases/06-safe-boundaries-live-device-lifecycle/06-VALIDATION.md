---
phase: 6
slug: safe-boundaries-live-device-lifecycle
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-03
reconstructed: true  # State B — authored retroactively from phase artifacts during /gsd-validate-phase
---

# Phase 6 — Validation Strategy

> Per-phase validation contract. Reconstructed retroactively (State B) from PLAN/SUMMARY/VERIFICATION
> artifacts and the executed test suite. Phase 6 requirements (DATA-01, DEV-05) all have automated
> verification; the two live-browser DEV-05 behaviors were additionally confirmed via Playwright UAT
> (see `06-UAT.md` tests 6 & 7, 2026-06-03).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework (backend)** | pytest 9.x + pytest-asyncio (real uvicorn + dev Postgres) |
| **Framework (frontend)** | vitest (jsdom) |
| **Config file** | `pyproject.toml` (pytest), `frontend/vitest.config.ts` |
| **Quick run command** | `uv run pytest tests/integration/test_two_profile_isolation.py` · `npm --prefix frontend run test -- KioskView.EventSource client.revoke` |
| **Full suite command** | `just test` (backend, 738+ passed) · `npm --prefix frontend run test` (149 passed) |
| **Estimated runtime** | backend ~3s (isolation file) / full ~minutes; frontend ~10s |

---

## Sampling Rate

- **After every task commit:** Run the relevant quick command (backend isolation file or frontend unit file).
- **After every plan wave:** Run the full suite for the touched layer.
- **Before `/gsd:verify-work`:** Full backend + frontend suites green.
- **Max feedback latency:** ~10s (quick) / full suite minutes.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01 | 01 | 1 | DATA-01 | T-06-01..04 | `write_boundary`/`fetch_current_boundary` scoped `WHERE profile_id=%s::uuid`; unbound→400; 0-row→404 | integration | `uv run pytest tests/integration/test_06_01_profile_scoped_writes.py tests/integration/test_06_01_write_callsite_scoping.py` | ✅ | ✅ green |
| 06-02 | 02 | 1 | DEV-05 (revoke) | T-06-05/06 | Kiosk `device_revoked` SSE / in-flight 403 → idempotent `triggerRevoke()` → App-level navigate `/pair`, mount-independent | unit | `npm --prefix frontend run test -- client.revoke` · `KioskView.EventSource` | ✅ | ✅ green |
| 06-02 | 02 | 1 | DEV-05 (reassign) | T-06-07 | `device_reassigned` → authoritative `getSession()` re-fetch → `setReassignBanner(display_name)` + SSE reconnect + query invalidation | unit | `npm --prefix frontend run test -- KioskView.EventSource` | ✅ | ✅ green |
| 06-03 | 03 | 2 | DATA-01 (proof) | T-06-08/09 | Two-profile isolation: A's write leaves B untouched; `boundary_changed` + `admin_editing` fan out per-profile only; phantom + admin reads + segment overrides per-profile | integration | `uv run pytest tests/integration/test_two_profile_isolation.py` (9 tests) | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

### Test → behavior detail (06-03, `test_two_profile_isolation.py`)

| Test | Truth covered |
|------|---------------|
| `test_boundary_edit_profile_a_does_not_touch_profile_b` | DATA-01 truth 3 (cross-profile isolation) |
| `test_unbound_admin_write_returns_400` | D-02 (unbound write rejected) |
| `test_zero_row_write_returns_404` | D-10 (absent position → 404) |
| `test_boundary_changed_fans_out_per_profile` | D-04 truth 4 (boundary_changed per-profile) |
| `test_admin_editing_fans_out_per_profile` | D-04 (editing shimmer per-profile) |
| `test_phantom_validation_is_per_profile` | phantom check scoped per-profile |
| `test_get_admin_cubes_returns_only_bound_profile` | admin cubes read scoped |
| `test_get_cube_boundary_returns_bound_profile_row` | admin boundary read scoped |
| `test_segment_overrides_isolation` | segment_overrides per-profile |

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements — pytest (backend integration, real server + Postgres) and vitest (frontend) were already in place; no new framework or fixture scaffolding was required for Phase 6.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Status |
|----------|-------------|------------|--------|
| Kiosk revoke → live "SCREEN REMOVED" overlay then navigate to `/pair` (real browser, real SSE timing) | DEV-05 | Unit tests prove the `triggerRevoke()`→navigate signal chain; the real-browser SSE delivery + 2.5s timer + navigation can only be *observed* live | ✅ Verified 2026-06-03 via Playwright (`06-UAT.md` test 6) |
| Kiosk reassign → "MOVED TO {name}" banner + live grid switch (two-profile runtime) | DEV-05 / T-06-07 | Unit tests prove the handler calls; the live re-bind + banner name from authoritative session needs a two-profile browser runtime | ✅ Verified 2026-06-03 via Playwright (`06-UAT.md` test 7) |

*Both manual behaviors also have unit-level coverage (signal paths) — they are listed here because the end-to-end live observation supplements the automated tests. Both have now been performed and passed.*

---

## Validation Sign-Off

- [x] All tasks have automated verify (pytest integration + vitest unit) or existing infrastructure
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (none — existing infra sufficient)
- [x] No watch-mode flags (`pytest` / `vitest run`)
- [x] Feedback latency acceptable (~10s quick)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-03 (retroactive validation; all DATA-01 + DEV-05 requirements have green automated coverage, live DEV-05 behaviors confirmed via Playwright UAT)

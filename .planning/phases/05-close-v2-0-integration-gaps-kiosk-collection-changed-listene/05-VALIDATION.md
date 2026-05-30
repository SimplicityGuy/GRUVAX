---
phase: 05
slug: close-v2-0-integration-gaps-kiosk-collection-changed-listene
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-30
---

# Phase 05 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Reconstructed retroactively (State B). Phase 5 was executed TDD (RED→GREEN), so every
> must-have behavior already carries a green automated test — no gaps to fill.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (backend) · vitest (frontend) |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) · `frontend/vite.config.ts` (test block) |
| **Quick run command** | `uv run pytest tests/integration/test_search_b02.py tests/integration/test_locate_b02.py -q` |
| **Full suite command** | `uv run pytest tests/ -q` && `cd frontend && npx vitest run` |
| **Estimated runtime** | ~15 s backend B-02 subset · ~6 s frontend EventSource subset |

Backend integration tests require the shared dev Postgres (`gruvax-dev-pg` at localhost:5432, seeded to head). The autouse `_seeded_profile_collection` fixture self-heals the schema and re-seeds `profile_collection` per module.

---

## Sampling Rate

- **After every task commit:** Run the quick run command (the changed endpoint's b02 tests / the EventSource test).
- **After every plan wave:** Run the full suite (`uv run pytest tests/ -q` + `npx vitest run`).
- **Before `/gsd:verify-work`:** Full suite green — confirmed (35 backend + frontend suites green at merge).
- **Max feedback latency:** ~20 s.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-T1 | 01 | 1 | API-02 | T-05-01/02 | RED tests: omitted `profile_id`→200; no-cookie→400 `session_unbound`; supplied-mismatch→403 `profile_mismatch` | integration | `uv run pytest tests/integration/test_search_b02.py tests/integration/test_locate_b02.py -q` | ✅ | ✅ green |
| 05-01-T2 | 01 | 1 | API-02 | T-05-01 | `/api/search` + `/api/locate` accept omitted `profile_id`, resolve cookie-authoritative profile, never trust client value over cookie | integration | `uv run pytest tests/integration/test_search_b02.py tests/integration/test_locate_b02.py tests/integration/test_search.py tests/integration/test_locate.py -q` | ✅ | ✅ green |
| 05-02-T1 | 02 | 1 | SYN-01, SYN-02, API-02 | T-05-03/04 | RED tests: `collection_changed`→invalidate `['search']`; search disabled when `boundProfileId` null | component | `cd frontend && npx vitest run src/routes/kiosk/KioskView.EventSource.test.tsx` | ✅ | ✅ green |
| 05-02-T2 | 02 | 1 | SYN-01, SYN-02 | T-05-03 | `collection_changed` listener busts `['search']` + `resync()` (`['units']`/`['cubes']`); `enabled` gated on `!!boundProfileId` | component | `cd frontend && npx vitest run src/routes/kiosk/KioskView.EventSource.test.tsx` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

### Must-have truth → test coverage

| Must-have truth | Covering test | Status |
|-----------------|---------------|--------|
| `/api/search` omitted `profile_id` + cookie → 200 scoped to bound profile (was 422) | `test_search_b02::test_omitted_profile_id_with_cookie` | ✅ |
| `/api/locate` omitted `profile_id` + cookie → 200 scoped to bound profile (was 422) | `test_locate_b02::test_omitted_profile_id_with_cookie` | ✅ |
| search/locate no cookie → 400 `session_unbound` | `test_{search,locate}_b02::test_no_cookie_returns_session_unbound` | ✅ |
| search/locate supplied mismatched `profile_id` → 403 `profile_mismatch` (no cross-profile leak) | `test_{search,locate}_b02::test_mismatched_profile_id_returns_403` | ✅ |
| `collection_changed` → kiosk invalidates `['search']` (live refetch) | `KioskView.EventSource.test.tsx` "collection_changed invalidates search query key (B-01)" | ✅ |
| `collection_changed` → kiosk resyncs `['units']`/`['cubes']` + re-locates | same test asserts `['units']`/`['cubes']` via `resync()` | ✅ |
| search query does not fire while `boundProfileId` is null | `KioskView.EventSource.test.tsx` "search query is disabled when boundProfileId is null (B-02)" | ✅ |

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. Phase 5 added no new framework — it extended the existing `tests/integration/` (pytest + LifespanManager + shared db_pool) and `frontend/src/routes/kiosk/KioskView.EventSource.test.tsx` (vitest) harnesses. RED tests were authored before implementation per the plan's TDD contract.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live end-to-end "Sync now → kiosk results refresh without reload" against a real running stack | SYN-01 Flow 4 | Component test proves the `collection_changed`→invalidate wiring; the full publisher→SSE→browser path is integration-level | Run the stack, trigger a profile sync, observe kiosk search results refresh without manual reload |

*All unit/component behaviors have automated verification; only the full live-stack SSE round-trip is manual (and is covered indirectly by the integration checker's seam analysis).*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (none — existing infra)
- [x] No watch-mode flags
- [x] Feedback latency < 20 s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-05-30

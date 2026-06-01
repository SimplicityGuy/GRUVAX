---
phase: 07
slug: member-self-connect-collection-diff
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-01
---

# Phase 07 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio (asyncio_mode=auto) for backend; ESLint + tsc for frontend |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]`; `frontend/eslint.config.*` + `frontend/tsconfig.json` |
| **Quick run command** | `uv run pytest tests/unit/ -q --tb=short --benchmark-skip` |
| **Full suite command** | `uv run pytest tests/ -q --tb=short --benchmark-skip` (backend) + `cd frontend && npm run lint && npx tsc --noEmit` |
| **Estimated runtime** | ~30–60 seconds backend; ~20 seconds frontend |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/ -q --tb=short --benchmark-skip` (backend tasks) or `npm run lint && npx tsc --noEmit` (frontend tasks)
- **After every plan wave:** Run the full backend suite `uv run pytest tests/ -q --tb=short --benchmark-skip` — MEMORY: phase contract changes can silently break Phase 1–6 tests; run the FULL sequential suite after each wave merge.
- **Before `/gsd:verify-work`:** Full backend suite green + frontend lint/tsc clean + human-verify checkpoint approved
- **Max feedback latency:** ~60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-01-00 | 01 | 1 | API-04 | T-07-SC | Test scaffolds for AUTH-02 + API-04 (Wave 0) | unit+integration | `uv run pytest tests/unit/test_profile_sync_diff.py tests/unit/test_fake_discogsography.py::test_limit_one -q --benchmark-skip` | ❌ W0 | ⬜ pending |
| 07-01-01 | 01 | 1 | API-04 | T-07-04 | first_seen_at nullable; invite table FK ON DELETE CASCADE | integration | `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head` | ❌ W0 | ⬜ pending |
| 07-01-02 | 01 | 1 | API-04 | T-07-01 / T-07-02 / T-07-03 | has_token derived (no ciphertext); count + is_initial atomic in swap; read last_sync_at IS NULL before UPDATE | integration | `uv run pytest tests/integration/test_invite_codes.py::test_initial_import_flag ::test_arrival_count_accuracy ::test_profile_new_record_fields ::test_profile_has_token_field tests/unit/test_profile_sync_diff.py -q --benchmark-skip` | ❌ W0 | ⬜ pending |
| 07-02-01 | 02 | 2 | AUTH-02 | T-07-05..T-07-11 | atomic single-use consume; pool-isolated PAT validate; Fernet store; uniform 404; per-IP rate limit | integration | `uv run mypy src/gruvax/api/invite_codes.py && uv run ruff check src/gruvax/api/invite_codes.py` | ❌ W0 | ⬜ pending |
| 07-02-02 | 02 | 2 | AUTH-02 | T-07-05/T-07-06/T-07-10 | owner route PIN-gated; public routes reachable + uniform 404 on used/expired/invalid | integration | `uv run pytest tests/integration/test_invite_codes.py -q --benchmark-skip` | ❌ W0 | ⬜ pending |
| 07-03-01 | 03 | 3 | AUTH-02 | T-07-13 | PAT only in state + POST body; type=password; not persisted client-side | static | `cd frontend && npm run lint && npx tsc --noEmit` | ✅ | ⬜ pending |
| 07-03-02 | 03 | 3 | AUTH-02 + API-04 | T-07-14/T-07-16 | owner sees only has_token; SSE parse try/catch graceful degrade; token-only CSS | static | `cd frontend && npm run lint && npx tsc --noEmit` | ✅ | ⬜ pending |
| 07-03-03 | 03 | 3 | AUTH-02 + API-04 | T-07-13/T-07-15 | end-to-end redeem + invite + diff indicators across 6 surfaces | manual | human-verify checkpoint (Local UAT recipe) | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/integration/test_invite_codes.py` — 12 tests covering AUTH-02 + API-04 (Plan-02 endpoint tests xfail-marked until Plan 02; API-04 tests pass after Plan 01). Created in Plan 01 Task 0.
- [ ] `tests/unit/test_profile_sync_diff.py` — unit tests for `new_record_count` arithmetic + `is_initial_import` detection + extended `collection_changed` payload. Created in Plan 01 Task 0.
- [ ] `tests/unit/test_fake_discogsography.py::test_limit_one` — confirm the CI fixture supports the `limit=1` PAT-validation call. Created in Plan 01 Task 0.

Framework already installed (pytest + pytest-asyncio + httpx + asgi-lifespan; frontend ESLint + tsc). No framework install needed.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Copy-to-clipboard "COPIED!" feedback + TTL countdown ticking | AUTH-02 | `navigator.clipboard` + setInterval visual behavior not unit-testable headlessly in this harness | Plan 03 human-verify checkpoint step 1 |
| Redeem page visual states + yellow focus ring + terminal success | AUTH-02 | Visual/interaction verification on a real device | Plan 03 human-verify checkpoint steps 2–3 |
| Kiosk yellow pill enter/exit + clears on next sync | API-04 | SSE-driven visual transition on the kiosk display | Plan 03 human-verify checkpoint step 5 |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (the one manual task is the explicit human-verify checkpoint)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (3 test files in Plan 01 Task 0)
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-01

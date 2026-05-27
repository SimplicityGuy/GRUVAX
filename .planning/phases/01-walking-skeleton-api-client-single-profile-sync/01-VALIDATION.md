---
phase: 1
slug: walking-skeleton-api-client-single-profile-sync
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-26
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Populated from RESEARCH.md §Validation Architecture. Planner refines per-task rows.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio + Hypothesis + pytest-benchmark + asgi-lifespan |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `just test-unit` (or `uv run pytest tests/unit -q`) |
| **Full suite command** | `just test` (or `uv run pytest -q`) |
| **Estimated runtime** | ~30s unit · ~90s full (incl. SLO benchmark) |

---

## Sampling Rate

- **After every task commit:** Run `just test-unit` for the touched module's directory
- **After every plan wave:** Run `just test` (full suite)
- **Before `/gsd-verify-work`:** Full suite must be green AND `just slo` (SLO benchmark) must pass with p95 ≤ 200 ms `/api/search`, ≤ 50 ms `/api/locate`
- **Max feedback latency:** 30 seconds (unit subset)

---

## Per-Task Verification Map

> Planner populates one row per task during PLAN.md generation. Use this skeleton.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | API-03 | — | Round-trip migration (upgrade → downgrade → upgrade) leaves schema identical | integration | `uv run alembic upgrade head && uv run alembic downgrade base && uv run alembic upgrade head` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 1 | API-01 | T-01-PAT-leak | `Authorization: Bearer dscg_*` substring never appears in any log record | unit | `uv run pytest tests/unit/discogsography/test_log_redaction.py -q` | ❌ W0 | ⬜ pending |
| 01-02-02 | 02 | 1 | API-01 | T-01-PAT-rest | Fernet round-trip: encrypt(plaintext) decrypts back to plaintext; ciphertext ≠ plaintext | unit | `uv run pytest tests/unit/discogsography/test_pat_crypto.py -q` | ❌ W0 | ⬜ pending |
| 01-02-03 | 02 | 1 | API-01 | — | 401/403 → `PATRejected`, no retry, app_token_revoked = TRUE; 429 → honors Retry-After + exp backoff max 3; 5xx → exp backoff max 3; network → 1 retry | unit | `uv run pytest tests/unit/discogsography/test_client_retry.py -q` | ❌ W0 | ⬜ pending |
| 01-03-01 | 03 | 2 | API-02, SYN-02 | — | `sync_profile(profile_id)` staging-swap leaves `profile_collection` consistent; advisory lock prevents concurrent runs | integration | `uv run pytest tests/integration/sync/test_sync_profile.py -q` | ❌ W0 | ⬜ pending |
| 01-03-02 | 03 | 2 | API-02 | — | Inline cache refresh: after sync, snapshot/segment/boundary caches reflect new data without process restart | integration | `uv run pytest tests/integration/sync/test_sync_cache_refresh.py -q` | ❌ W0 | ⬜ pending |
| 01-04-01 | 04 | 3 | PROF-03 | T-01-PAT-stdin | `gruvax-set-pat` reads PAT only from stdin (no --pat flag, no env fallback); mismatched user_id exits non-zero | integration | `uv run pytest tests/integration/cli/test_set_pat.py -q` | ❌ W0 | ⬜ pending |
| 01-04-02 | 04 | 3 | PROF-03 | T-01-admin-pin | `gruvax-sync` requires admin PIN; `POST /api/admin/profiles/{id}/sync` returns 401 without auth | integration | `uv run pytest tests/integration/cli/test_sync_cli.py -q tests/integration/api/test_admin_sync_endpoint.py -q` | ❌ W0 | ⬜ pending |
| 01-05-01 | 05 | 3 | SYN-02 | — | `/api/health` returns `discogsography_api_check` (not `..._view_check`); states map per D-13 | integration | `uv run pytest tests/integration/api/test_health.py -q` | ❌ W0 | ⬜ pending |
| 01-05-02 | 05 | 3 | — | — | Compose `up` reaches `gruvax-api` healthy with `fake-discogsography` sibling serving the contract endpoints | manual | `docker compose up -d && docker compose ps` | ❌ W0 | manual |
| 01-06-01 | 06 | 4 | API-02 | — | SLO benchmark passes: `/api/search` p95 ≤ 200 ms and `/api/locate` p95 ≤ 50 ms on synthetic data | benchmark | `just slo` | ✅ (exists from v1.0) | ⬜ pending |
| 01-06-02 | 06 | 4 | API-02 | — | After v_collection → profile_collection rewire, all 5 query functions (search_collection, get_release_for_locate, get_sync_staleness_seconds, get_phantom_boundary_count, snapshot.load) return identical results | unit | `uv run pytest tests/unit/db/test_queries_rewire.py -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Files / fixtures planner MUST create as Wave 0 BEFORE the implementation waves begin:

- [ ] `tests/unit/discogsography/__init__.py` + fixture layout for the DiscogsographyClient + Fernet + log-redactor specs
- [ ] `tests/integration/sync/__init__.py` + per-test temp-schema bootstrap for `sync_profile` tests
- [ ] `tests/integration/cli/__init__.py` + subprocess harness for the two new CLIs
- [ ] `tests/fixtures/fake_discogsography.py` — in-memory FastAPI app implementing `/api/user/collection` (paged), `/api/user/collection/stats`, `/api/user/collection/timeline`; supports token-routing, 401/403/429/5xx triggers via magic tokens / query params
- [ ] `tests/fixtures/synth_profile_collection.sql` — replaces v1's `tests/fixtures/synth_collection.sql`; seeds `gruvax.profile_collection` with the ~3000-row synthetic dataset for the default profile UUID
- [ ] `tests/fixtures/discogsography_payloads/` — recorded contract envelopes (one with `has_more=true`, one terminal, one rate-limited with `Retry-After`, one 401)
- [ ] `tests/conftest.py` additions: `fake_discogsography_app`, `fake_discogsography_client` (httpx.AsyncClient against ASGITransport), `default_profile_uuid` fixtures
- [ ] CI job: Alembic round-trip check (`upgrade head && downgrade base && upgrade head`) — extend existing v1.0 CI matrix

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Compose-up clean-boot: `gruvax-api` healthy, `fake-discogsography` sibling running, init-sync container populated `profile_collection` for default profile | API-02, PROF-03 | Multi-container orchestration; CI doesn't run docker compose | `docker compose up -d; docker compose ps; docker compose exec gruvax-api curl -s localhost:8080/api/health \| jq` |
| Kiosk staleness banner: data source rewires correctly under three D-13 states (`ok`, `failed`, `stale`) | SYN-02 | Visual / browser interaction | Open kiosk in Chromium; with default profile fresh-synced banner is hidden; manipulate `profiles.last_sync_at` via psql to simulate >14d stale → banner shows v1.0 copy "Collection data may be outdated — last synced {Xd} ago" |
| `gruvax-set-pat` interactive paste flow (no echo, no history leak) | PROF-03 | TTY interaction | Run `gruvax-set-pat --profile default` in TTY; paste PAT at prompt; verify `~/.zsh_history` (or `~/.bash_history`) does NOT contain the PAT |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s for unit subset
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

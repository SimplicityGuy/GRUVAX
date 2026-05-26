---
phase: 08
slug: observability-deployment-hardening
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-24
---

# Phase 08 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at plan time (all 6 PLANs carried a `<threat_model>` block); this audit **verifies mitigations exist** rather than scanning for new threats.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| LAN client → GET /api/version | Public, unauthenticated endpoint on a LAN-only box | git SHA / build timestamp / environment (non-secret) |
| LAN client → GET /api/health | Public, unauthenticated; subsystem status + version + staleness | status flags, git SHA, `sync_age_seconds` |
| Kiosk SPA → GET /api/health | Public health read; only `sync_age_seconds` is consumed for the banner | whole-day staleness age |
| LAN client → GET /api/admin/diagnostics | Admin-only; exposes pool stats, timings, ring-buffer log lines | release_id-keyed counts + display fields + log messages |
| LAN client → POST /api/admin/diagnostics/reset-stats | Admin-only destructive write (TRUNCATEs counters) | none (action only) |
| Search/locate path → gruvax.record_stats | Server-side counter writes from search/locate handlers | int `release_id` only |
| Query functions → gruvax.v_collection | Read-only discogsography contact surface (Pitfall 5) | collection read fields (view only) |
| Background task → gruvax.v_collection | Sync-age refresh reads discogsography sync timestamp | `max(synced_at)` aggregate |
| Log records → in-memory log ring buffer | `gruvax.*` log lines accumulate in memory, read via admin diagnostics | counts/timing messages (no query text / PIN) |
| Docker build args → image filesystem | Build-time metadata baked into `_version.py` (gitignored) | git SHA / build timestamp / environment |
| CI runner → repo fixtures | CI seeds the DB; synthetic data only, never the real collection CSV | `fixtures/synth_collection.sql` |
| Compose log driver → host disk | Container logs written to `lux` disk; bounded to avoid disk exhaustion | json-file logs (≤30 MB/service) |
| Docker image / CI → baked secrets | `SESSION_SECRET` in CI is a throwaway literal, never a real secret | non-production test literal |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation (evidence) | Status |
|-----------|----------|-----------|-------------|-----------------------|--------|
| T-08-01 | Information Disclosure | GET /api/version | mitigate | Body is exactly `git_sha`/`build_timestamp`/`environment`. `src/gruvax/api/version.py:38-44`; `tests/integration/test_version.py:116-118` asserts key set. | closed |
| T-08-02 | Information Disclosure | log ring buffer | mitigate | `JsonFormatter.format()` uses `record.getMessage()` only; `LogRingHandler.emit()` stores only `ts/level/logger/msg`. `src/gruvax/logging_config.py:47-56,79-90`. Ring scoped to `gruvax.*` (`app.py:100`); no query text / PIN logged in `search.py`/`queries.py`. | closed |
| T-08-03 | Denial of Service | sync-age refresh task | accept | 60s cadence, single-row aggregate over ≤3K rows; every iteration wrapped in `try/except`, sets `None` on failure, never raises. `src/gruvax/app.py:214-241`. Soundness verified. | closed |
| T-08-04 | Tampering | package installs | mitigate | No `pyproject.toml`/`uv.lock`/`frontend/package.json` changes in plan-01 commits. | closed |
| T-08-05 | Information Disclosure | record_stats schema | mitigate | No `query`/`term`/`text` column. `migrations/versions/0008_record_stats.py:28-38`; `tests/unit/test_stats.py:35-59` asserts via `information_schema.columns`. | closed |
| T-08-06 | Injection (SQL) | new queries.py functions | mitigate | All six functions use `%s` placeholders, no f-string interpolation. `src/gruvax/db/queries.py:927,952-967,986-1001,1023-1038,1063-1076,1093`. | closed |
| T-08-07 | Information Disclosure | discogsography data access | mitigate | All reads via `gruvax.v_collection` only; zero `collection_items` references. `src/gruvax/db/queries.py:927,1033,1068`. | closed |
| T-08-08 | Tampering | package installs | mitigate | No dependency-file changes in plan-02 commits. | closed |
| T-08-09 | Information Disclosure | GET /api/health body | mitigate | Body = status/db/discogsography_view_check/mqtt/version/started_at/sync_age_seconds; no secrets. `src/gruvax/api/health.py:55-63`; `tests/integration/test_health.py:136-143`. | closed |
| T-08-10 | Information Disclosure | counter increment args | mitigate | Only `int release_id` reaches `increment_*`. `src/gruvax/api/search.py:71`; `src/gruvax/api/locate.py:121`. | closed |
| T-08-11 | Denial of Service | fire-and-forget counter tasks | mitigate | `asyncio.create_task` + strong-ref `app.state.background_tasks` + `_log_exc` done-callback; never delays/crashes response. `search.py:71-91`, `locate.py:121-141`. | closed |
| T-08-12 | Tampering | package installs | mitigate | No dependency-file changes in plan-03 commits. | closed |
| T-08-13 | Elevation of Privilege | reset-stats POST | mitigate | `Depends(require_admin)` enforces session + CSRF double-submit. `src/gruvax/api/admin/diagnostics.py:111-115`; `src/gruvax/api/deps.py:170-177`; `tests/integration/test_diagnostics.py:192-199` (401/403). | closed |
| T-08-14 | Information Disclosure | diagnostics GET body | mitigate | Body = 7 SC#2 fields only; no connection strings/env/PIN/raw query text. `diagnostics.py:100-108`; `tests/integration/test_diagnostics.py:166-179`. | closed |
| T-08-15 | Information Disclosure | recent_logs row | mitigate | Sourced from `app.state.log_ring_buffer` (`diagnostics.py:65-66`); ring stores only `ts/level/logger/msg` scoped to `gruvax.*`; admin-gated read. | closed |
| T-08-16 | Tampering | package installs | mitigate | No dependency-file changes (backend or frontend) in plan-04 commits. | closed |
| T-08-17 | Information Disclosure | kiosk banner copy | mitigate | Copy = "Collection data may be outdated — last synced {N}d ago"; whole-day only, no jargon/internal fields. `frontend/src/routes/kiosk/StalenessBar.tsx:58`. | closed |
| T-08-18 | Denial of Service | kiosk health refetch | accept | 60s `refetchInterval` against `app.state`-only health read (no per-request DB hit); LAN-local single client; negligible. `KioskView.tsx:76-78`, `health.py`. Soundness verified. | closed |
| T-08-19 | Tampering | package installs | mitigate | No `frontend/package.json` changes in plan-05 commits. | closed |
| T-08-20 | Information Disclosure | CI dataset | mitigate | Seed step is `fixtures/synth_collection.sql` only; no real CSV / `background/` path anywhere in workflow. `.github/workflows/ci.yml:94`. | closed |
| T-08-21 | Denial of Service | host disk via container logs | mitigate | `json-file` driver `max-size 10m` + `max-file 3` (~30 MB) on `api`/`gruvax-dev-pg`/`mosquitto`. `compose.yaml:91-95,128-131,153-157`. | closed |
| T-08-22 | Information Disclosure | CI SESSION_SECRET | accept | Literal test string `"ci-test-secret-not-real"`, not a `${{ secrets.* }}` reference; no production credential present. `.github/workflows/ci.yml:56`. Soundness verified. | closed |
| T-08-23 | Tampering | package installs | mitigate | `uv sync --frozen` enforces lockfile (`ci.yml:75`); plan-06 commits add only `pyproject.toml` `addopts` config (non-dependency). | closed |
| T-08-24 | Tampering | GitHub Actions versions | mitigate | Maintained latest actions (`checkout@v4`, `setup-uv@v6`, `setup-python@v5`) + `permissions: contents: read`. `.github/workflows/ci.yml:30-31,60,63,68`. | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-08-01 | T-08-03 | Sync-age refresh: 60s cadence over a single-row aggregate of ≤3K rows is negligible load; failures are caught/logged and set to null, never crashing startup or blocking requests. Condition holds at `app.py:214-241`. | gsd-security-auditor (verified) | 2026-05-24 |
| AR-08-02 | T-08-18 | Kiosk health refetch: 60s interval reading only from `app.state` (zero DB hit per request), LAN-local single client. Condition holds at `health.py` (no DB calls) + `KioskView.tsx:76-78`. | gsd-security-auditor (verified) | 2026-05-24 |
| AR-08-03 | T-08-22 | CI `SESSION_SECRET` is a literal non-production test string, not a `${{ secrets.* }}` reference; no production credential exposed. Condition holds at `ci.yml:56`. | gsd-security-auditor (verified) | 2026-05-24 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-24 | 24 | 24 | 0 | gsd-security-auditor (sonnet) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-24

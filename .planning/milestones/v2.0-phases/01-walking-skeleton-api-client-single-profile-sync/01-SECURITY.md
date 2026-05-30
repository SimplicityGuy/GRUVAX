---
phase: 01
slug: walking-skeleton-api-client-single-profile-sync
status: verified
threats_total: 51
threats_closed: 51
threats_open: 0
asvs_level: 1
created: 2026-05-30
---

# Phase 01 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| developer machine → committed fixture | Synthetic test data only | Deterministic generator output; no PII |
| generator script → committed YAML/SQL | Deterministic; same seed produces same bytes | Shape-variety synthetic records |
| operator → settings | Operator-controlled env vars read at process boot | GRUVAX_SECRET_KEY (Fernet key), DISCOGSOGRAPHY_BASE_URL |
| migration → DB | DDL/DML operations run with elevated DB role | Schema + seed row |
| GRUVAX → discogsography HTTP | Bearer PAT egress over LAN HTTP | PAT (Fernet-encrypted at rest); collection data |
| operator stdin → CLI process | PAT input via terminal paste or pipe | Plaintext PAT (ephemeral in process memory) |
| CLI process → discogsography HTTP | Test-sync GET egress with Bearer PAT | PAT |
| CLI process → GRUVAX admin HTTP | PIN-authenticated POST to sync endpoint | PIN (JSON body), session cookie |
| sync_profile → DB | DDL (CREATE TEMP TABLE) + DML (COPY, DELETE, INSERT, UPDATE) | Collection rows, PAT ciphertext |
| concurrent sync_profile invocations | Advisory lock sole serialization primitive | Profile UUID |
| /api/health response → external clients | Cached state; no PII | Sync timestamps, status flags |
| compose-time init-sync → admin endpoint | GRUVAX_ADMIN_PIN in env | Admin PIN |
| fake-discogsography container ↔ api container | Internal compose network only | Synthetic seed data |
| pytest fixture → dev Postgres | Sync psycopg connection with dev DATABASE_URL | Synthetic SQL fixture |
| pytest harness → alembic subprocess | Child process with inherited env | DATABASE_URL |
| query layer ↔ DB | All SQL parameterized | profile_id + search terms |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-00-fixture-drift | Tampering | YAML seed and SQL fixture diverge | mitigate | Single canonical generator emits both; row-count regression test enforces equality | closed |
| T-00-fake-module-drift | Tampering | Separate fake-app implementations in services/ and tests/ | mitigate | Single canonical module at src/gruvax/_internal/fake_discogsography.py; both consumers import directly | closed |
| T-00-legacy-collision | Tampering | Plan 01 and Plan 06 both reference fixtures/synth_collection.sql | mitigate | Wave 0 pre-moves legacy seed to tests/fixtures/legacy/ before any wave-1+ plan runs | closed |
| T-00-secret-leak-in-fixture | Information Disclosure | Synthetic data contains a real PAT | accept | Fake user_id is a fixed sentinel; no dscg_* tokens generated; PII-free by construction | closed |
| T-01-PAT-rest (Plan 01) | Information Disclosure | gruvax.profiles.app_token_encrypted | mitigate | BYTEA column stores Fernet ciphertext only; seed row uses '\x'::bytea + app_token_revoked=TRUE | closed |
| T-01-supply-chain (Plan 01) | Tampering | New runtime deps cryptography, stamina | mitigate | RESEARCH §Package Legitimacy Audit verified both packages [OK] via slopcheck | closed |
| T-01-migration-partial | Tampering | Alembic upgrade/downgrade partial-failure | mitigate | alembic env.py uses transaction_per_migration=True; CI round-trip gate | closed |
| T-01-secret-leak-via-repr | Information Disclosure | settings.GRUVAX_SECRET_KEY accidentally logged | mitigate | Declared as SecretStr; pydantic repr shows '**********' only | closed |
| T-01-malformed-key-boot | Denial of Service | Operator pastes invalid GRUVAX_SECRET_KEY | accept | field_validator calls Fernet(key); raises ValueError at boot with clear error; fail-fast convention | closed |
| T-01-downgrade-failure | Tampering | Downgrade can't re-create v_collection (Pitfall 5) | mitigate | Migration 0009 downgrade issues SET LOCAL search_path = gruvax, gruvax_dev, public before CREATE VIEW | closed |
| T-01-PAT-leak | Information Disclosure | structlog event_dict values containing Authorization headers or PAT plaintext | mitigate | redact_dscg_tokens slotted into shared_processors BEFORE format_exc_info; broader regex covers exception message substrings | closed |
| T-01-PAT-rest (Plan 02) | Information Disclosure | PAT plaintext leaving process memory | mitigate | pat_crypto.encrypt_pat (Fernet AES-128-CBC + HMAC) is the only DB-write path; decrypt_pat raises on InvalidToken | closed |
| T-01-PAT-cross-key | Tampering | GRUVAX_SECRET_KEY rotation orphans existing rows | accept | decrypt_pat raises InvalidToken → sync sets last_sync_status='failed' + last_sync_error='pat_rejected'; operator re-issues PAT via gruvax-set-pat | closed |
| T-01-rate-limit-DoS | Denial of Service | Runaway retry loop hammers discogsography | mitigate | stamina caps at 4 total attempts (3 retries); 401/403 short-circuits with zero retries; 429 honors Retry-After | closed |
| T-01-error-shape-leak | Information Disclosure | Exception message leaks PAT or DB internals | mitigate | All typed errors carry only operator-safe strings; PATRejected raised with fixed message never echoing PAT | closed |
| T-01-fake-drift (Plan 02) | Tampering | services/fake-discogsography/ and tests/fixtures/ with separate fake-app implementations | mitigate | Single canonical module; both consumers (test fixtures + Plan 05 Compose sibling) import directly from src/gruvax/_internal/fake_discogsography.py | closed |
| T-01-supply-chain (Plan 02) | Tampering | stamina, cryptography, pytest-httpx packages | mitigate | RESEARCH §Package Legitimacy Audit verified [OK] for all three | closed |
| T-01-staging-swap-partial | Tampering | profile_collection in indeterminate state on swap failure | mitigate | DELETE+INSERT+UPDATE wrapped in async with conn.transaction() (single TX); staging TEMP table is ON COMMIT DROP | closed |
| T-01-lock-leak | Denial of Service | Advisory lock not released on exception (Pitfall 1) | mitigate | try/finally pg_advisory_unlock guarantees release; stale-lock detection (5-minute threshold) | closed |
| T-01-pool-exhaust | Denial of Service | Long-running sync holds a pool slot (Pitfall 6) | mitigate | Dedicated psycopg.AsyncConnection.connect() for sync body; pool slot only briefly used for cache-refresh | closed |
| T-01-PAT-rotation-silent | Tampering | sync writes a new discogsography_user_id on PAT rotation | mitigate | sync_profile uses COALESCE(existing, captured) — preserves original user_id; strict user_id match enforced by gruvax-set-pat | closed |
| T-01-key-rotation | Information Disclosure | GRUVAX_SECRET_KEY changed → existing PATs un-decryptable | mitigate | decrypt_pat raises InvalidToken → sync sets last_sync_status='failed' + last_sync_error='pat_rejected' + app_token_revoked=TRUE | closed |
| T-01-sqli-staging | Tampering | f-string SQL in staging-swap re-introduces injection | mitigate | All DML uses %s placeholders; static DDL (CREATE TEMP TABLE) has no user input | closed |
| T-01-sentinel-pat-call | Information Disclosure | Empty-placeholder PAT actually hits discogsography | mitigate | Pitfall 8 sentinel detection short-circuits BEFORE constructing DiscogsographyClient | closed |
| T-01-admin-pin | Spoofing | POST /api/admin/profiles/{id}/sync without auth | mitigate | Depends(require_admin) on the handler — session + CSRF + sliding TTL inherited from v1 | closed |
| T-01-pool-block-on-sync | Denial of Service | Handler injects Depends(get_pool), holds pool slot for sync duration | mitigate | Handler uses request.app.state.db_pool in tight async-with block for 404 pre-flight, CLOSES the block, THEN awaits sync_profile | closed |
| T-01-PAT-stdin | Information Disclosure | PAT leakage via shell history / ps / journald | mitigate | D-07 enforced: stdin-only, no --pat flag, no env fallback, getpass when TTY | closed |
| T-01-PAT-rotation (Plan 04) | Tampering | Cross-user PAT silently overwrites a profile | mitigate | D-09 strict user_id match in set_pat CLI; on mismatch CLI exits non-zero with exact wording before any DB write | closed |
| T-01-PAT-leak (CLI 401 path) | Tampering | 401 response from test-sync silently corrupts the profile row (Pitfall 2) | mitigate | set_pat CLI's 401 branch sys.exits BEFORE the DB UPDATE | closed |
| T-01-csrf-bypass | Tampering | gruvax-sync CLI bypasses CSRF | mitigate | CLI captures CSRF from login response and echoes it in X-CSRF-Token header | closed |
| T-01-pat-disclosure-on-error | Information Disclosure | CLI error messages leak PAT plaintext | mitigate | DiscogsographyClient never echoes PAT in PATRejected; set_pat CLI sys.exit messages reference only profile names + user_ids | closed |
| T-01-pin-disclosure | Information Disclosure | gruvax-sync logs the PIN | mitigate | getpass-only input when TTY; readline-only when pipe; CLI never logs the pin variable | closed |
| T-01-health-leak | Information Disclosure | /api/health reveals last_sync_at timestamps | accept | LAN-only deployment (OOS-06); timestamps reveal sync cadence but not PAT or user data; matches v1 contract | closed |
| T-01-init-sync-pin | Information Disclosure | GRUVAX_ADMIN_PIN in compose env | mitigate | Sourced from .env (gitignored); compose uses ${GRUVAX_ADMIN_PIN:?...} substitution that fails compose-up clearly if missing | closed |
| T-01-init-sync-rerun | Tampering | init-sync re-syncs unnecessarily on every boot | mitigate | D-16 verbatim — precheck COUNT(*) on profile_collection; skip if populated | closed |
| T-01-fake-svc-exposure | Spoofing | fake-discogsography exposed externally | mitigate | Bound to internal network only; no ports: mapping; only reachable via Compose DNS | closed |
| T-01-fake-leak-prod | Tampering | fake-discogsography accidentally runs in prod | mitigate | Distinct compose service name + dev-only; prod overrides DISCOGSOGRAPHY_BASE_URL; documented in compose.yaml header | closed |
| T-01-fake-drift (Plan 05) | Tampering | Compose sibling and tests/ have separate fake-app implementations | mitigate | Single canonical module at src/gruvax/_internal/fake_discogsography.py (D-15); server.py imports directly; no copy in services/ | closed |
| T-01-lifespan-crash | Denial of Service | profile_collection probe failure crashes startup | mitigate | try/except + logger.error + proceed pattern preserved; app.state.profile_collection_ready flipped without crashing | closed |
| T-01-fake-token-pollution | Tampering | Production code accidentally uses dscg_dev_seed | accept | Token hard-coded only in fake service's Dockerfile healthcheck; production GRUVAX never has this token in profile rows | closed |
| T-01-sqli-rewire | Tampering | Rewire reintroduces f-string SQL | mitigate | All %s placeholders preserved in queries.py; 16 confirmed profile_id = %s::uuid bindings | closed |
| T-01-slo-regression | Denial of Service | profile_collection slower than v_collection | mitigate | Migration 0009 ships all required indexes (GIN fts, composite (profile_id, label, catalog_number), GIN trgm) | closed |
| T-01-cross-profile-read | Information Disclosure | Missing profile_id binding leaks other-profile data | mitigate | Every query binds DEFAULT_PROFILE_UUID; all 13 FROM gruvax.profile_collection occurrences confirmed present | closed |
| T-01-fixture-pollution | Tampering | Synthetic fixture leaks into production DB | accept | Fixture is local-dev/test only (compose mount :ro); production seeds only via sync_profile | closed |
| T-01-pitfall-c-loss | Tampering | Estimator stops casefolding labels (Pitfall C regression) | mitigate | label.casefold() preserved in collection_snapshot.py load(); never calls normalize_catalog() on labels | closed |
| T-01-07-01 | Tampering | tests/integration/conftest.py seed path | accept | Synth SQL is a committed fixture under repo control; modifications surface in git diff; no write paths to production | closed |
| T-01-07-02 | Denial of Service | Repeated TRUNCATE+INSERT against dev DB | accept | ~3000 INSERTs per module ≈ <200ms on localhost; dev DB only; production unaffected | closed |
| T-01-07-03 | Information Disclosure | boundaries.yaml in git history | accept | Fixture is fully synthetic; no real catalog numbers or artist names; same disclosure posture as v1 | closed |
| T-01-08-01 | Denial of Service | Stuck alembic subprocess hanging the test session | mitigate | timeout=120 on subprocess.run raises subprocess.TimeoutExpired if alembic does not return within 2 minutes | closed |
| T-01-08-02 | Tampering | Malicious DATABASE_URL injection via test env | accept | Subprocess inherits os.environ; same exposure as existing just migrate-roundtrip shell recipe in CI | closed |
| T-01-08-03 | Information Disclosure | subprocess stdout/stderr captured in pytest report | accept | Alembic output may include SQL/table names but never plaintext PATs or session secrets; pytest report is dev/CI-only | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01-00-01 | T-00-secret-leak-in-fixture | Synthetic fixture uses a fixed UUID sentinel (99999999-...) as user_id; no dscg_* tokens appear in generator output or emitted SQL/YAML. No real PATs. | gsd-security-auditor | 2026-05-30 |
| AR-01-01-01 | T-01-malformed-key-boot | Boot-time fail-fast on invalid GRUVAX_SECRET_KEY is the declared behavior; operator sees the error and re-generates. Same convention as DATABASE_URL. | gsd-security-auditor | 2026-05-30 |
| AR-01-02-01 | T-01-PAT-cross-key | On key rotation decrypt_pat raises InvalidToken which surfaces as a loud failure (last_sync_status='failed', app_token_revoked=TRUE). Rotation utility deferred to a later phase per CONTEXT.md. | gsd-security-auditor | 2026-05-30 |
| AR-01-05-01 | T-01-health-leak | /api/health timestamp exposure is intentional; LAN-only deployment (OOS-06); reveals sync cadence only, not PAT or user data. Matches v1 contract. | gsd-security-auditor | 2026-05-30 |
| AR-01-05-02 | T-01-fake-token-pollution | dscg_dev_seed hard-coded only in services/fake-discogsography/Dockerfile CMD healthcheck line; absent from src/gruvax/ entirely. Production never loads this token into profile rows. | gsd-security-auditor | 2026-05-30 |
| AR-01-06-01 | T-01-fixture-pollution | Compose mount is :ro and referenced only in gruvax-dev-pg initdb section; production deploys do not mount dev fixtures. | gsd-security-auditor | 2026-05-30 |
| AR-01-07-01 | T-01-07-01 | Committed test fixture; no PII; repo-controlled. Any modification visible via git diff. | gsd-security-auditor | 2026-05-30 |
| AR-01-07-02 | T-01-07-02 | Dev-only overhead (~200ms per module); does not affect production. | gsd-security-auditor | 2026-05-30 |
| AR-01-07-03 | T-01-07-03 | boundaries.yaml is fully synthetic; same disclosure posture as v1.0 Phase 8 committed fixture. | gsd-security-auditor | 2026-05-30 |
| AR-01-08-01 | T-01-08-02 | Subprocess inherits os.environ; identical exposure surface to the existing justfile migrate-roundtrip recipe which CI already runs. No new injection vector. | gsd-security-auditor | 2026-05-30 |
| AR-01-08-02 | T-01-08-03 | Alembic stdout/stderr in pytest report includes DDL/table names only. No PAT, session secrets, or PII flows through migration output. Dev/CI-only surface. | gsd-security-auditor | 2026-05-30 |

*Accepted risks do not resurface in future audit runs.*

---

## Unregistered Threat Flags

The following items appeared in SUMMARY.md `## Threat Flags` sections but were not raised as new attack surface without an existing threat mapping:

- **01-00-SUMMARY.md**: "None" — no unregistered flags.
- **01-02-SUMMARY.md**: "None" — all surfaces (PAT egress, log redaction, Fernet at-rest) already in the threat register.
- **01-05-SUMMARY.md**: init-sync PIN and fake-svc-exposure flags map to T-01-init-sync-pin and T-01-fake-svc-exposure respectively (registered).
- **01-06-SUMMARY.md**: sqli-rewire, slo-regression, cross-profile-read, fixture-pollution, pitfall-c-loss all map to registered threats.
- **01-07-SUMMARY.md**: "None" — no unregistered flags.

No `unregistered_flag` entries.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-30 | 51 | 51 | 0 | gsd-security-auditor |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-30

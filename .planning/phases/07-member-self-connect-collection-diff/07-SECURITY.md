---
phase: 7
slug: 07-member-self-connect-collection-diff
status: verified
threats_total: 18
threats_closed: 18
threats_open: 0
asvs_level: L2
created: 2026-06-01
---

# Phase 07 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| admin browser → /api/admin/profiles, /api/admin/diagnostics | PIN-gated (require_admin + CSRF); must never leak encrypted/raw PAT | Profile metadata, derived has_token bool, diff counts |
| sync worker → Postgres swap transaction | Diff count must be committed atomically with the collection swap | new_record_count, is_initial_import, profile row UPDATE |
| member browser (untrusted) → POST /api/invite-codes/{code}/redeem | PUBLIC endpoint accepting a secret (member PAT) | PAT, redeem code UUID |
| member browser → GET /api/invite-codes/{code} | PUBLIC code-validation endpoint; must not become enumeration oracle | display_name, expires_at |
| invite_codes server → discogsography HTTP | Outbound PAT validation; PAT must not be logged or leaked | PAT (in Authorization header only) |
| invite_codes server → Postgres | Encrypted-at-rest PAT store; atomic single-use consume | Fernet ciphertext |
| member browser → public redeem page /redeem/:code | RedeemPage POSTs the PAT to the public endpoint; must not persist PAT client-side | PAT (component state + POST body only) |
| owner browser → admin invite affordance | Owner must never see the raw/encrypted PAT; only derived presence | has_token bool, invite URL + TTL |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-07-01 | Information Disclosure | GET /api/admin/profiles + /diagnostics | mitigate | has_token derived in SQL as `(app_token_encrypted IS NOT NULL AND length(app_token_encrypted) > 1)::bool AS has_token`; ciphertext excluded from all SELECT projections and response dicts | closed |
| T-07-02 | Tampering | _swap_inside_tx arrival count | mitigate | new_record_count and is_initial_import computed inside the swap transaction; last_new_record_count and last_sync_is_initial stored atomically in the same profiles UPDATE | closed |
| T-07-03 | Repudiation/Integrity | is_initial_import detection | mitigate | `last_sync_at IS NULL` read BEFORE the UPDATE that sets it; Pitfall 4 ordering enforced | closed |
| T-07-04 | Information Disclosure | first_seen_at backfill | accept | Nullable online ADD COLUMN; diff uses scalar pre-DELETE COUNT(*) join, not per-row first_seen_at; no PII in column; see Accepted Risks Log | closed |
| T-07-SC-01 | Tampering | supply chain (Plan 01) | mitigate | No new packages added; tech-stack.added: [] confirmed in 07-01-SUMMARY.md | closed |
| T-07-05 | Elevation of Privilege | invite code brute-force/enumeration | mitigate | UUID4 (gen_random_uuid) = 122-bit entropy; _REDEEM_RATE = parse_limit("5/10minutes") enforced per-IP with namespace "invite_redeem"; GET /invite-codes/{code} returns uniform 404 and never echoes the code | closed |
| T-07-06 | Tampering | replay / double-redeem | mitigate | Atomic `UPDATE ... WHERE code = %s::uuid AND consumed_at IS NULL AND expires_at > NOW() RETURNING profile_id`; second request matches no row under READ COMMITTED (first wins) | closed |
| T-07-07 | Information Disclosure | PAT exposure via API response | mitigate | Redeem returns only {status, profile_id}; PAT never echoed; admin API exposes derived has_token only (Plan 01) | closed |
| T-07-08 | Information Disclosure | PAT exposure via logs + response | mitigate | No log/detail string built from body.pat; all 503 handlers use static literal message ("Discogs is temporarily unavailable..."), not str(exc) — WR-02 fix verified at invite_codes.py:342-353; structlog log_redactor masks dscg_* as defence-in-depth | closed |
| T-07-09 | Information Disclosure | PAT confidentiality at rest | mitigate | encrypt_pat() (Fernet/AES-128-CBC + HMAC-SHA256) called before bytea write; pat_crypto.py verified; plaintext never reaches Postgres | closed |
| T-07-10 | Information Disclosure | oracle: expired vs used vs invalid | mitigate | All negative invite cases — expired, consumed, invalid UUID, non-existent — return identical 404 {type: invite_not_found}; _parse_invite_uuid, _CONSUME_INVITE, _SELECT_INVITE all funnel to the same 404 response | closed |
| T-07-11 | Denial of Service | pool exhaustion via concurrent redeems | mitigate | Pool-isolation discipline: _run_test_sync HTTP call runs between Step 1 (consume, pool released) and Step 3 (collision check, pool acquired) — no pool slot held during HTTP call; per-IP rate limit caps abuse | closed |
| T-07-12 | Spoofing | redeem onto profile with existing token | accept | D-10 intentional rotate; COALESCE preserves existing user_id; only owner can mint single-use TTL invite; see Accepted Risks Log | closed |
| T-07-LAN | Information Disclosure | PAT over plaintext HTTP on LAN | accept | L-05 locked: home-LAN-only, no public exposure; L-05 runbook documented in 07-02-SUMMARY.md; TLS required if ever exposed beyond LAN; see Accepted Risks Log | closed |
| T-07-SC-02 | Tampering | supply chain (Plan 02) | mitigate | No new packages added; tech-stack.added: [] confirmed in 07-02-SUMMARY.md | closed |
| T-07-13 | Information Disclosure | RedeemPage PAT handling | mitigate | PAT in component state only; input type="password" autocomplete="off" (RedeemPage.tsx:215,222); never written to localStorage/sessionStorage/URL (no such writes found); POST body only | closed |
| T-07-14 | Information Disclosure | owner invite affordance | mitigate | ProfileDrawer INVITE LINK section shows only inviteInfo.url and TTL countdown; no PAT field or value in the invite flow; owner sees presence via has_token bool only (types.ts:395) | closed |
| T-07-15 | Information Disclosure | error-card oracle on redeem page | accept | Member-facing copy is safe; backend returns uniform 404 regardless (T-07-10); frontend mapRedeemError collapses invite_not_found to generic "not valid" copy; see Accepted Risks Log | closed |
| T-07-16 | Tampering | kiosk SSE payload parse | mitigate | collection_changed handler upgraded to `(e: MessageEvent)`; JSON.parse wrapped in try/catch with graceful degrade; no es.close() inside handler — only cleanup return at KioskView.tsx:408 calls es.close() | closed |
| T-07-SC-03 | Tampering | supply chain (Plan 03) | mitigate | No new packages added; tech-stack.added: [] confirmed in 07-03-SUMMARY.md | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-07-01 | T-07-04 | first_seen_at backfill: nullable online ADD COLUMN is the correct Alembic online-migration pattern. Existing rows retain NULL. Diff count uses scalar pre-DELETE COUNT(*) join (not per-row first_seen_at) so NULL backfill cannot mis-count on the first post-migration sync. No PII in the column. | phase plan (register_authored_at_plan_time: true) | 2026-06-01 |
| AR-07-02 | T-07-12 | Redeeming onto a profile that already has a token overwrites/rotates it (D-10). This is intentional: only the owner can mint a single-use, 1-hour TTL invite for that specific profile. An attacker cannot generate an invite without a valid admin PIN session. The deliberate overwrite is safe within the trust model. | phase plan (register_authored_at_plan_time: true) | 2026-06-01 |
| AR-07-03 | T-07-LAN | The member PAT travels over plaintext HTTP during POST /api/invite-codes/{code}/redeem. Acceptable for home-LAN-only deployment with no public exposure (L-05 constraint). HTTPS is required if the API is ever exposed beyond the LAN. Documented as L-05 runbook note in 07-02-SUMMARY.md. | phase plan (register_authored_at_plan_time: true) | 2026-06-01 |
| AR-07-04 | T-07-15 | The redeem page error card shows "expired" vs "already used" copy that could technically distinguish code states to a member. This discriminator is safe: the owner who minted the code already knows the state; an attacker cannot enumerate code validity because the server returns a uniform 404 for all negative cases regardless of the UI copy shown. | phase plan (register_authored_at_plan_time: true) | 2026-06-01 |

---

## Unregistered Threat Flags

All three SUMMARY.md files (07-01, 07-02, 07-03) declare "No new threat surfaces introduced beyond those already in the plan's threat register." No unregistered flags require logging.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-01 | 18 | 18 | 0 | gsd-security-auditor (claude-sonnet-4-6) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-01

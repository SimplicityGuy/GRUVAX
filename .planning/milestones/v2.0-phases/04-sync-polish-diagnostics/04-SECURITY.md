---
phase: 04
slug: sync-polish-diagnostics
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-29
---

# Phase 04 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Phase 4 added the nightly autonomous sync scheduler, soft-delete purge, the
> `sync.cadence` admin setting, the `needs_reauth` session signal, the
> per-profile admin diagnostics payload, and the kiosk re-auth banner UI.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| nightly loop → discogsography API | Server-side outbound HTTP carrying the Fernet-decrypted PAT as a Bearer token | PAT (secret) |
| admin client → PUT /api/admin/settings | PIN-gated write of `sync.cadence` (untrusted value crosses here) | cadence enum |
| soft-delete caller → purge DELETE | `profile_id` flows into a DELETE on `gruvax.profile_collection` | server-derived UUID |
| kiosk/SPA → GET /api/session | `needs_reauth` exposed per bound profile | per-profile boolean |
| admin client → GET /api/admin/diagnostics | PIN-gated read of per-profile sync metadata | sync status/timestamps/counts/error-tags |
| kiosk browser → ReauthBanner | `needs_reauth` consumed to render public-facing banner | non-technical copy only |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-04-00-01 | Tampering | test SQL fixtures | accept | Test-only code; parameterized `%s` SQL retained; no production surface | closed |
| T-04-00-SC | Tampering | npm/pip installs | accept | Zero new packages (04-RESEARCH §Package Legitimacy Audit) | closed |
| T-04-01-01 | Information Disclosure | `_sync_loop` / catch-up sweep logs | mitigate | `dscg_*` structlog redactor + nightly logs pass only `profile_id`+status, never the PAT — verified `nightly.py:197,200,260,262,288,321` | closed |
| T-04-01-02 | Tampering | purge DELETE on `profile_collection` | mitigate | Parameterized `%s::uuid` only, server-derived UUID, no FK cascade — verified `nightly.py:317` | closed |
| T-04-01-03 | Tampering | `sync.cadence` settings write | mitigate | Validate against `_CADENCE_VALUES` frozenset + `_ALLOWED_SETTINGS_KEYS` whitelist before SQL, 422 on invalid — verified `settings.py:49,106,278–298` | closed |
| T-04-01-04 | Information Disclosure | `needs_reauth` on /api/session | mitigate | Derived only from the caller's bound profile; no cross-profile leakage — verified `session.py:165–170` | closed |
| T-04-01-05 | Elevation of Privilege | stale `app_token_revoked` | mitigate | `needs_reauth` derived from live per-request profiles read, not an `app.state` cache — verified `session.py:100–114,164–170` | closed |
| T-04-01-06 | Denial of Service | startup catch-up sync-storm vs rate limit | accept | Sequential per-profile + skip policy (≤4 profiles ≈ 60 req/min); DiscogsographyClient 429+Retry-After backoff is the safety valve | closed |
| T-04-01-SC | Tampering | npm/pip installs | accept | Zero new packages (04-RESEARCH §Package Legitimacy Audit) | closed |
| T-04-02-01 | Information Disclosure | `profiles[]` sync metadata | mitigate | Behind `require_admin`; payload carries only sync status/timestamps/counts/error-tags, no PAT/secret; `last_sync_error` is a fixed tag enum — verified `diagnostics.py:48,112–123` | closed |
| T-04-02-02 | Information Disclosure | cross-profile data (admin view) | accept | Admin endpoint intentionally lists all non-deleted profiles (single-owner admin context; OOS-04 restricts non-admin per-session reads, not the admin view) | closed |
| T-04-02-SC | Tampering | npm/pip installs | accept | Zero new packages (04-RESEARCH §Package Legitimacy Audit) | closed |
| T-04-03-01 | Information Disclosure | kiosk re-auth banner copy | mitigate | Non-technical copy; zero "PAT"/"token"/"API key" strings on the public kiosk — verified `ReauthBanner.tsx:49` | closed |
| T-04-03-02 | Tampering | `sync_cadence` PUT value (frontend) | mitigate | Backend validates against `_CADENCE_VALUES` (422); frontend `<select>` constrains to four fixed options, no free text — verified `settings.py:282`, `Settings.tsx:385–395` | closed |
| T-04-03-03 | Information Disclosure | diagnostics cards | accept | Behind `require_admin`; displays only sync metadata, no secrets | closed |
| T-04-03-SC | Tampering | npm installs | mitigate | Zero new packages this phase — verified `package.json`/`pyproject.toml` unmodified across all 7 Phase 4 commits | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-04-01 | T-04-00-01 | Test-only SQL fixtures; no production surface | Robert Wlodarczyk | 2026-05-29 |
| AR-04-02 | T-04-00-SC / T-04-01-SC / T-04-02-SC | Zero new packages added this phase (per 04-RESEARCH Package Legitimacy Audit) | Robert Wlodarczyk | 2026-05-29 |
| AR-04-03 | T-04-01-06 | Startup catch-up storm bounded by sequential per-profile iteration + skip policy (≤4 profiles); 429+Retry-After backoff is the safety valve | Robert Wlodarczyk | 2026-05-29 |
| AR-04-04 | T-04-02-02 | Admin diagnostics intentionally lists all non-deleted profiles — single-owner admin context | Robert Wlodarczyk | 2026-05-29 |
| AR-04-05 | T-04-03-03 | Diagnostics cards behind `require_admin`, sync metadata only, no secrets | Robert Wlodarczyk | 2026-05-29 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-29 | 16 | 16 | 0 | gsd-security-auditor (sonnet) |

### Security Audit 2026-05-29

| Metric | Count |
|--------|-------|
| Threats found | 16 |
| Closed | 16 |
| Open | 0 |

9 mitigate-disposition threats verified present in implementation (file:line evidence in
register above); 7 accept-disposition threats confirmed as documented risks. Register was
authored at plan time across all four 04-*-PLAN.md `<threat_model>` blocks
(`register_authored_at_plan_time: true`) — auditor ran in verify-mitigations mode, not
retroactive-STRIDE.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-29

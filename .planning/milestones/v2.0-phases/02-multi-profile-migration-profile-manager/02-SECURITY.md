---
phase: 02
slug: multi-profile-migration-profile-manager
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-30
---

# Phase 02 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| test harness → DB | Tests connect to the shared dev Postgres; fixtures clean up rows they insert | Profile rows (display_name, UUID) |
| migration → production DB | DDL runs with schema-owner privileges; PK changes lock tables | profile_id NOT NULL constraints, composite PKs |
| client → per-profile endpoint | Untrusted path `profile_id` enters here; validated against browse-binding cookie | profile_id (UUID string) |
| sync background task → in-memory registry | A sync mutates only its own profile's registry slot | BoundaryCache, CollectionSnapshot, SegmentCache, EventBus |
| LAN browser → /api/session, /api/session/bind | No-PIN browse-binding; binding validated server-side | profile UUID cookie |
| browse-binding cookie ↔ admin PIN session | Two independent cookies; must not couple (D2-10) | gruvax_browse_binding vs gruvax_session |
| admin browser → /api/admin/profiles/* | PIN-gated mutations; pasted PAT crosses here | PAT plaintext (in-flight), encrypted bytes (stored) |
| GRUVAX → discogsography | Bearer PAT sent on test-sync; must never be logged in plaintext | PAT, discogsography_user_id |
| kiosk browser → /api/events/{profile_id}, /api/search, /api/locate | Untrusted path/query profile_id; validated against browse-binding cookie, never authoritative | profile_id, search query |
| admin browser → /api/admin/profiles/* (UI) | PIN-gated; pasted PAT entered in drawer | PAT (in-flight only; not returned by GET) |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-02-00-01 | Tampering | second_profile fixture leaves orphan rows | mitigate | Fixture teardown soft-deletes the seeded profile (UPDATE deleted_at = now()); suite stays order-independent | closed |
| T-02-00-SC | Tampering | npm/pip installs | accept | No package installs in plan (Wave 0 test-only) | closed |
| T-02-01-01 | Denial of Service | DROP/ADD PRIMARY KEY on data tables | accept | Household scale; ACCESS EXCLUSIVE lock is sub-second on ~3k rows; no zero-downtime requirement | closed |
| T-02-01-02 | Tampering | NULL profile_id slipping past the tighten | mitigate | Per-table `_VERIFY_NO_NULLS` DO-block RAISEs EXCEPTION before SET NOT NULL | closed |
| T-02-01-03 | Tampering | downgrade leaving inconsistent PK/nullability state | mitigate | `just migrate-roundtrip` CI gate + test_roundtrip_clean asserts exit 0 | closed |
| T-02-01-SC | Tampering | npm/pip installs | accept | No package installs | closed |
| T-02-02-01 | Spoofing | path profile_id in `*_for_profile` deps | mitigate | Deps validate path profile_id == browse-binding cookie; 403 on mismatch, 400 on unbound (D2-04) | closed |
| T-02-02-02 | Information Disclosure | cross-profile cache reads via registry mis-key | mitigate | Registry resolved by str(profile_id); distinct keys → distinct instances — isolation by construction | closed |
| T-02-02-03 | Information Disclosure | collection_changed published before cache reload (stale read race) | mitigate | `_refresh_profile_caches` enforces invalidate→load→publish ordering (Pitfall A); source-order verified | closed |
| T-02-02-04 | Elevation of Privilege | bus resolution dep reaching into the pool | mitigate | `get_bus_for_profile` reads only app.state (Pitfall 10 preserved); no get_pool dependency | closed |
| T-02-02-SC | Tampering | npm/pip installs | accept | No package installs | closed |
| T-02-03-01 | Information Disclosure | SSE delivering another profile's events | mitigate | Per-profile EventBus registry resolved by validated profile_id; get_bus_for_profile 403s on mismatch | closed |
| T-02-03-02 | Spoofing | profile_id in search/locate/illuminate path/query | mitigate | Per-profile resolution deps validate path profile_id == browse cookie before returning the cache (403/400) | closed |
| T-02-03-03 | Information Disclosure | search/locate reading default profile's collection regardless of binding | mitigate | profile_id passed into every query AND DEFAULT_PROFILE_UUID default removed from search_collection/get_release_for_locate/did_you_mean_query (TypeError on missing arg — D2-04) | closed |
| T-02-03-04 | Elevation of Privilege | SSE endpoint coupling to the DB pool | mitigate | events.py depends only on get_bus_for_profile; grep confirms zero get_pool references in the file | closed |
| T-02-03-SC | Tampering | npm/pip installs | accept | No package installs | closed |
| T-02-04-01 | Spoofing | forged gruvax_browse_binding cookie | mitigate | Server validates bound profile_id against active-profiles set / registry on every per-profile endpoint; forged id → 404/403 in get_*_for_profile deps | closed |
| T-02-04-02 | Spoofing | admin-session confused with browse-binding | mitigate | Distinct cookie names (gruvax_session vs gruvax_browse_binding); require_admin reads only gruvax_session/gruvax_csrf; session.py endpoints carry no require_admin | closed |
| T-02-04-03 | Information Disclosure | GET /api/session leaking secrets (PAT) in profiles[] | mitigate | Bootstrap SELECT (_SELECT_ACTIVE_PROFILES) excludes app_token_encrypted and discogsography_user_id; returns only display_name + sync metadata | closed |
| T-02-04-04 | Tampering | CSRF on bind/unbind | accept | SameSite=Strict on both cookies + same-site-only LAN traffic blocks cross-site POST; bind/unbind are non-destructive (reversible via picker). Admin mutations keep existing CSRF double-submit. | closed |
| T-02-04-SC | Tampering | npm/pip installs | accept | No package installs | closed |
| T-02-05-01 | Spoofing | unauthenticated profile mutation | mitigate | Every POST/PATCH/DELETE under /api/admin/profiles requires require_admin (PIN session + CSRF double-submit) at lines 186, 239, 285, 402, 436, 534, 626 | closed |
| T-02-05-02 | Information Disclosure | PAT plaintext at rest or in logs | mitigate | encrypt_pat (Fernet) before storage; structlog dscg_* redactor masks Bearer tokens; GET /profiles SELECT excludes app_token_encrypted | closed |
| T-02-05-03 | Tampering | one discogsography user mapped to two profiles | mitigate | Connect captures user_id; 409 user_id_collision via uq_profiles_dgs_user_id_active partial-unique index + explicit pre-check (D-09 strict match); rotate requires same-user match | closed |
| T-02-05-04 | Tampering | background sync exception silently lost | mitigate | _run_sync_background catch-all + logger.exception; last_sync_status flips to 'failed' (Pitfall 3); the poll surfaces 'failed' | closed |
| T-02-05-05 | Denial of Service | multi-second sync starving the pool | mitigate | Pitfall 6 pool discipline preserved: tight preflight checkout released before the long test-sync call; no Depends(get_pool) in profile_sync.py; 202 returns before sync runs | closed |
| T-02-05-06 | Elevation of Privilege | stale browse binding to a soft-deleted profile | mitigate | Soft-delete pops all six registry entries via _evict_profile_registries (profiles.py:162-177, called at line 668); per-profile deps return 404 for evicted profiles (D2-03) | closed |
| T-02-05-SC | Tampering | npm/pip installs | accept | No package installs | closed |
| T-02-06-01 | Spoofing | SPA sending a profile_id it isn't bound to | mitigate | Server-side per-profile deps 403 on mismatch (Plans 02-02/02-03); SPA only uses cookie-bound id | closed |
| T-02-06-02 | Information Disclosure | picker exposing PAT/secret in profiles[] | mitigate | GET /api/session returns only display_name + sync metadata (enforced server-side, Plan 02-04); SPA renders only those fields | closed |
| T-02-06-03 | Tampering | XSS via profile display_name in cards | mitigate | All strings rendered via JSX interpolation, never innerHTML (confirmed: no innerHTML in ProfilePickerCard, ProfilePicker, ProfilesManager) | closed |
| T-02-06-SC | Tampering | npm installs | mitigate | No new npm packages; lucide-react, TanStack Query, Zustand all already locked | closed |
| T-02-07-01 | Information Disclosure | PAT visible/leaked in the UI | mitigate | PAT input type="password" + Eye/EyeOff show/hide toggle (aria-label "Show token"/"Hide token"); API never returns stored PAT | closed |
| T-02-07-02 | Spoofing | CSRF on profile mutations | mitigate | All mutations send X-CSRF-Token via adminClient.ts (double-submit, carries from v1); require_admin enforces it server-side | closed |
| T-02-07-03 | Tampering | XSS via profile display_name in cards/drawer | mitigate | All strings via JSX interpolation, never innerHTML (confirmed: no innerHTML in ProfileDrawer, ProfileCard) | closed |
| T-02-07-04 | Information Disclosure | raw HTTP error codes / stack detail shown to the owner | mitigate | Error type discriminators mapped to UI-SPEC friendly plain-language copy; no status codes surfaced | closed |
| T-02-07-SC | Tampering | npm installs | mitigate | No new npm packages (lucide-react / TanStack Query / Zustand already locked) | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-02-01 | T-02-01-01 | ACCESS EXCLUSIVE lock during DROP/ADD PRIMARY KEY is sub-second at household scale (~3k rows). Zero-downtime DDL patterns are unnecessary here. | Phase 02 executor | 2026-05-28 |
| AR-02-02 | T-02-04-04 | SameSite=Strict + LAN-only traffic is sufficient CSRF protection for the non-destructive, reversible browse-binding endpoints. Admin mutations keep the existing CSRF double-submit. | Phase 02 executor | 2026-05-28 |

*Accepted risks do not resurface in future audit runs.*

---

## Unregistered Flags

| Flag | Source | Description | Assessment |
|------|--------|-------------|------------|
| threat_flag: new_endpoint | 02-05-SUMMARY.md | 7 new admin endpoints under /api/admin/profiles | Maps to T-02-05-01 (all gated by require_admin). Informational — no new threat mapping required. |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-30 | 36 | 36 | 0 | gsd-security-auditor (claude-sonnet-4-6) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-30

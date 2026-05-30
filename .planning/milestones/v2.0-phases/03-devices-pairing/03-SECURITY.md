---
phase: 03
slug: devices-pairing
status: verified
threats_total: 21
threats_closed: 21
threats_open: 0
asvs_level: 1
created: 2026-05-30
---

# Phase 03 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| dev machine → PyPI | Package install of playwright + pytest-playwright | Third-party code (dev-only) |
| kiosk browser → API | fingerprint cookie on every request | Session-equivalent credential |
| API → Postgres | device rows, pairing_codes rows | FK to profiles; fingerprint stored plain |
| admin browser → /api/admin/devices/* | PIN-session-gated mutations | Pairing codes, device lifecycle |
| admin → /api/admin/devices/bind | Brute-force target (10k code keyspace) | 4-digit pairing code |
| Pi disk (user-data-dir) → reboot | Cookie persistence across power cycle | gruvax_device_fp cookie value |
| systemd --user → Chromium | Supervised kiosk process | Process lifecycle |
| kiosk SPA → /api/devices/* | Server-issued code; never reads HttpOnly fingerprint | Pairing code (non-secret) |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-03-SC | Tampering | playwright + pytest-playwright install | mitigate | Blocking human checkpoint in 03-00 Plan Task 1; human verified both packages on pypi.org before `uv add`; dev-group only | closed |
| T-03-01 | Spoofing | fingerprint cookie value | mitigate | `secrets.token_urlsafe(32)` CSPRNG at sessions.py:300; `httponly=True` at sessions.py:321 | closed |
| T-03-02 | Information Disclosure | fingerprint value in logs | mitigate | No logger calls reference fp value in sessions.py, devices.py, admin/devices.py, or deps.py; comments explicitly prohibit it | closed |
| T-03-03 | Tampering | session-cookie losing persistence (no max_age) | mitigate | `max_age=FINGERPRINT_MAX_AGE` (30×24×3600 = 2,592,000 s) set in sessions.py:327; enforced by unit test | closed |
| T-03-04 | Elevation of Privilege | revoked-device fingerprint lookup misses revoked rows | mitigate | Non-partial `idx_devices_fingerprint` index on gruvax.devices(fingerprint) in migration 0011:119-121 | closed |
| T-03-05 | Elevation of Privilege | bind code brute-force | mitigate | `_check_bind_rate_limit` called as first line of bind_device at admin/devices.py:261; `_BIND_RATE = parse_limit("10/5minutes")` at limiter.py:45; `Depends(require_admin)` also required | closed |
| T-03-06 | Tampering | concurrent bind race on one code | mitigate | Atomic `UPDATE pairing_codes SET consumed_at=NOW() WHERE code=%s AND consumed_at IS NULL AND expires_at > NOW() RETURNING fingerprint` at admin/devices.py:80-87 | closed |
| T-03-07 | Spoofing | unauthenticated admin mutation | mitigate | Every admin handler has `_admin: dict[str, Any] = Depends(require_admin)` — bind, list, patch, revoke, reinstate, delete at admin/devices.py:245,344,380,475,513,540 | closed |
| T-03-08 | Information Disclosure | fingerprint leaked in list/bind response or logs | mitigate | `_LIST_DEVICES` and `_SELECT_DEVICE_BY_ID` never SELECT fingerprint column (admin/devices.py:119-129); `_row_to_device` never includes fingerprint (admin/devices.py:201-212) | closed |
| T-03-09 | Spoofing | client-supplied profile_id trusted on bind | accept | Documented in Accepted Risks Log below | closed |
| T-03-10 | Elevation of Privilege | client-supplied profile_id on per-profile request | mitigate | `resolve_profile_from_request` derives profile_id from device binding / browse cookie server-side at deps.py:179-233; never trusts path param | closed |
| T-03-11 | Elevation of Privilege | revoked device still served (missed SSE) | mitigate | `device_revoked` 403 raised in deps.py:212-215 on every per-profile request; independent of SSE delivery | closed |
| T-03-12 | Information Disclosure | cross-profile data leak via stale binding | mitigate | `profile_mismatch` 403 retained in every per-profile dep at deps.py:271-275,305-309,337-341,378-382; orphaned device falls to browse-binding fallback, never another profile | closed |
| T-03-13 | Denial of Service | SSE dep holds pool for stream lifetime | mitigate | Pool acquired+released inside `get_bus_for_profile` dep at deps.py:375-395; generator body in events.py:58-77 reads only asyncio.Queue — zero pool holding | closed |
| T-03-14 | Information Disclosure | fingerprint value exposed in session payload or logs | mitigate | session.py:172-178 content includes only `device_id` (non-secret UUID) and `is_device_paired`; fingerprint never serialized | closed |
| T-03-15 | Information Disclosure | fingerprint read by client JS | mitigate | `httponly=True` set on cookie at sessions.py:321; PairView.tsx contains no `document.cookie` access or fingerprint read; SPA only ever sees `device_id` from GET /api/session | closed |
| T-03-16 | Spoofing | unauthenticated access to admin device UI | mitigate | `/admin/*` routes behind `AdminShell` which renders `PinOverlay` when `isLoggedIn === false` (AdminShell.tsx:315); all mutations routed to PIN-gated backend endpoints | closed |
| T-03-17 | Tampering | client bypasses revoke by ignoring SSE | accept | Documented in Accepted Risks Log below | closed |
| T-03-18 | Availability | session cookie lost on reboot (re-pair forced) | mitigate | `max_age=30d` at sessions.py:327 + `--user-data-dir="$USER_DATA_DIR"` on SD card (non-tmpfs) at start-kiosk.sh:40; proven by Playwright persistent-context test | closed |
| T-03-19 | Availability | kiosk process dies and stays down | mitigate | `Restart=always` + `RestartSec=3` in gruvax-kiosk.service:9-10 | closed |
| T-03-20 | Information Disclosure | fingerprint cookie readable off the Pi disk | accept | Documented in Accepted Risks Log below | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-03-01 | T-03-09 | Bind sets profile_id only via PIN-gated admin input. Non-admin per-profile resolution derives profile_id from server-side device binding in resolve_profile_from_request (deps.py:179-233) — the client-supplied profile_id on bind is validated by a PIN-authed admin and defaulted to DEFAULT_PROFILE_UUID when absent. No client can self-assign a profile without admin action. | Phase 03 executor + auditor | 2026-05-30 |
| AR-03-02 | T-03-17 | UI revoke optimistic update is convenience only. The backend per-request revoke guard (deps.py:212-215) denies a revoked device's next per-profile request with HTTP 403 device_revoked — independent of whether the SPA processes the SSE event. A revoked kiosk that ignores SSE still cannot access protected data after the next request. The accept is bounded: SSE delivery lag is bounded by the poll interval and is not a security gap. | Phase 03 executor + auditor | 2026-05-30 |
| AR-03-03 | T-03-20 | LAN-only deployment (no public exposure). The fingerprint cookie is HttpOnly (inaccessible to JS) and revocable server-side at any time — physical theft of the SD card yields a token the admin can instantly invalidate. Physical access to the Pi hardware is outside the household threat model for v1 (OOS-06). Risk will be re-evaluated if TLS is introduced or the deployment scope changes. | Phase 03 executor + auditor | 2026-05-30 |

*Accepted risks do not resurface in future audit runs.*

---

## Unregistered Threat Flags

All threat flags in SUMMARY.md `## Threat Flags` sections map to registered threats or are explicitly declared as no new surface:

| Plan | Threat Flags Entry | Mapping |
|------|-------------------|---------|
| 03-00 | "None. This plan adds only test files and dev-only dependencies." | No new surface; T-03-SC covers playwright install |
| 03-01 | "No new network endpoints, auth paths, or file access patterns beyond what was planned." | All within T-03-01..T-03-04 |
| 03-02 | "No new threat surface beyond what was planned in the threat model." | All within T-03-05..T-03-09 |
| 03-03 | Explicit per-threat mapping table (T-03-10..T-03-14 all addressed) | All within T-03-10..T-03-14 |
| 03-04 | "No new threat surface beyond what was planned." Explicit note T-03-15 mitigated, T-03-16 mitigated, T-03-17 accepted. | All within T-03-15..T-03-17 |
| 03-05 | "No new threat surface introduced." Addresses T-03-18 and T-03-19 as planned. | All within T-03-18..T-03-20 |

None of the executor-reported threat flags are unregistered.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-30 | 21 | 21 | 0 | gsd-security-auditor (claude-sonnet-4-6) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log (AR-03-01, AR-03-02, AR-03-03)
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-30

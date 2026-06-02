---
phase: 9
slug: offline-reconnect-ux
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-02
---

# Phase 9 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
>
> Scope: offline/reconnect UX for the home-LAN-only GRUVAX kiosk (FastAPI SSE backend
> + React/Zustand/TanStack Query frontend). No public exposure. Threat register
> authored at plan time across plans 09-01/02/03; verified retroactively by
> gsd-security-auditor.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| kiosk browser → `/api/events/{profile_id}` SSE | Long-lived connection; untrusted client may reconnect repeatedly | Reconnect interval (`retry_ms`), event payloads (no auth material) |
| browser network state → TanStack Query / kiosk UI gating | `navigator.onLine` is an untrustworthy connectivity signal on a LAN (PITFALLS 35); SSE state is the real signal | Connectivity truth (`sseConnected`), cosmetic copy hint |
| client-side control gating → server | Disabling controls is UX, NOT a security boundary; server-side authz remains the control | UI enable/disable flags only |
| SSE `device_revoked` event → terminal device state | A revoked device must reach its terminal state even while the offline banner could render | Device revocation signal |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-09-01 | Denial of Service | SSE reconnect after server restart | mitigate | Per-connection `retry:` jitter (2000–8000 ms) on the SSE generator's initial frame — `src/gruvax/api/events.py:65–66` (`random.randint(2000, 8000)`) | closed |
| T-09-02 | Denial of Service | Single client opening many SSE connections | accept | Home-LAN only; `finally: bus.unsubscribe(q)` reclaims per-connection queue on every disconnect — `events.py:79` | closed |
| T-09-03 | Information Disclosure | `retry_ms` observable by client | accept | By-design, non-sensitive; SSE frame carries only the reconnect integer, no PII/auth — `events.py:66` | closed |
| T-09-04 | Denial of Service | Reconnect refetch storm via `refetchOnReconnect` | mitigate | `networkMode: 'always'` on QueryClient default options — `frontend/src/App.tsx:29` | closed |
| T-09-05 | Spoofing | `navigator.onLine=true` while server down (false connectivity) | mitigate | Connectivity truth = `sseConnected`; `bannerVisible = !connected && everConnected`; `navigator.onLine` never read in store — `store.ts:197`, `OfflineBanner.tsx:46` | closed |
| T-09-06 | Tampering | Client-side store mutation of `bannerVisible` | accept | Client UX state, not a security boundary; server-side authz is the real control | closed |
| T-09-07 | Elevation of Privilege | Client-side gating of search / profile-switch / cube taps | accept | UX gating only (`SearchBox.tsx:91` `disabled={isOffline}`); server authz (admin PIN, device binding from Phase 6) enforced independently | closed |
| T-09-08 | Denial of Service | `device_revoked` terminal path masked by offline banner | mitigate | `device_revoked` handler calls `triggerRevoke()` unconditionally, no banner guard — `KioskView.tsx:460–461`; `App.tsx:122–134` drives `RevokeNotice` + `/pair` nav independently | closed |
| T-09-09 | Spoofing | `navigator.onLine=true` masking real server outage | mitigate | Banner renders on `!bannerVisible` (SSE-derived only); `navigator.onLine` selects copy text only — `OfflineBanner.tsx:46,49` | closed |
| T-09-10 | Tampering | Stale cache served as fresh / dismissed diff badge re-appearing | mitigate | `resync()` includes `invalidateQueries(['search'])` (09-04), called from `onopen` + `server_hello`; `newRecordState` local state untouched by resync → dismissed badge stays dismissed — `KioskView.tsx:318,342,407` | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-09-01 | T-09-02 | Home-LAN only, no public exposure (CLAUDE.md Connectivity constraint); low-value internal target; per-connection resources reclaimed via `bus.unsubscribe` on disconnect | Robert Wlodarczyk | 2026-06-02 |
| AR-09-02 | T-09-03 | The reconnect interval is non-sensitive and must be readable by the browser by design; no PII or auth material in the frame | Robert Wlodarczyk | 2026-06-02 |
| AR-09-03 | T-09-06 | `bannerVisible` is client-side UX state, not a security boundary; server-side authz remains the real control; a tampered flag cannot grant access | Robert Wlodarczyk | 2026-06-02 |
| AR-09-04 | T-09-07 | Control gating is UX only; bypass cannot reach data the server would not already serve; server-side authz (admin PIN, device binding from Phase 6) is unaffected | Robert Wlodarczyk | 2026-06-02 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-02 | 10 | 10 | 0 | gsd-security-auditor (sonnet) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-02

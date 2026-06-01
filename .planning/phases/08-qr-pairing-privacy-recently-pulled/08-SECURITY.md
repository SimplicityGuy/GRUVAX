---
phase: 08
slug: qr-pairing-privacy-recently-pulled
status: secured
threats_open: 0
threats_total: 13
threats_closed: 13
asvs_level: 1
created: 2026-06-01
---

# SECURITY.md — Phase 08: QR Pairing + Privacy + Recently-Pulled

**Audit Date:** 2026-06-01
**ASVS Level:** L1
**Auditor:** gsd-security-auditor (claude-sonnet-4-6)
**Phase Directory:** `.planning/phases/08-qr-pairing-privacy-recently-pulled/`
**Verdict:** SECURED — 14/14 threats closed, 0 open

---

## Threat Verification

### Plan 08-01 — Privacy CI-Lock (Backend)

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-08-01 | Information Disclosure | mitigate | CLOSED | `src/gruvax/api/search.py:131-136` — the fire-and-forget counter only passes `top_id` (int `release_id`) to `increment_search_count`; `q` is never logged. Comment at line 131 explicitly states "PRIVACY: only the int release_id is passed — never q, did_you_mean, or label text." `tests/integration/test_08_privacy.py:73-100` (`test_query_never_in_logs`) drives a live ASGI request and asserts PROBE_TERM absent from every `app.state.log_ring_buffer` entry. |
| T-08-02 | Information Disclosure | mitigate | CLOSED | `src/gruvax/logging_config.py:188` — `logging.getLogger("uvicorn.access").setLevel(logging.WARNING)` is present as a direct call in `configure_logging()`. `tests/integration/test_08_privacy.py:103-126` (`test_uvicorn_access_log_suppressed`) asserts `uvicorn.access` level `>= logging.WARNING` after lifespan runs. |
| T-08-03 | Information Disclosure | mitigate | CLOSED | `tests/integration/test_08_privacy.py:129-163` (`test_no_search_log_table`) — resolves the active schema at runtime via `SELECT current_schema()`, then calls `to_regclass('{schema}.search_log')` and asserts the result is NULL. Works for both `gruvax` and `gruvax_dev` schemas. |

### Plan 08-02 — QR Pairing (Frontend)

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-08-QR-01 | Information Disclosure | mitigate | CLOSED | `frontend/src/routes/kiosk/PairView.tsx:311` — QR `value` is `${window.location.origin}/admin/devices?code=${pairingCode.code}`. Only the 4-digit code is encoded in the URL. No PIN, no PAT, no session token. |
| T-08-QR-02 | Elevation of Privilege | mitigate | CLOSED | `src/gruvax/api/admin/devices.py:82-85` — `UPDATE pairing_codes SET consumed_at = NOW() WHERE ... AND consumed_at IS NULL AND expires_at > NOW()`. Atomic first-wins conditional UPDATE; zero rows returned on stale/replayed code → maps to `code_not_found` 404. 5-minute TTL enforced by `expires_at > NOW()`. Physical confirmation (phone scan with stale code → mapBindError UI) deferred to 08-HUMAN-UAT.md. |
| T-08-QR-03 | Elevation of Privilege | mitigate | CLOSED | `frontend/src/routes/admin/DeviceDrawer.tsx:315-323` — the prefill confirm screen renders the code in a `<p>` element with an explicit CTA button. No `useEffect` calls `handleBind` on mount when `prefillCode` is present. The only `handleBind` call sites in prefill mode are the `onClick` of the "PAIR THIS DEVICE" button (line 457) and the "Enter a different code" path which drops to manual entry. No auto-submit. Physical confirmation deferred to 08-HUMAN-UAT.md. |
| T-08-QR-04 | Spoofing/EoP | mitigate | CLOSED | `frontend/src/routes/admin/AdminShell.tsx:148,315` — `showOverlay = !isLoggedIn \|\| isLocked`; when true, `<PinOverlay>` is rendered as a full-page modal overlay. The `/admin/devices` route is a child of `AdminShell`, so scanning the QR and landing on `/admin/devices?code=...` renders PinOverlay blocking the entire viewport. The `?code=` URL param survives (not stripped until after PIN entry, per DevicesManager's mount-read useEffect which only runs after the route mounts inside the authenticated Outlet). Physical confirmation deferred to 08-HUMAN-UAT.md. |
| T-08-QR-05 | Repudiation | mitigate | CLOSED | `frontend/src/routes/admin/DeviceDrawer.tsx:124-139` — single `handleBind` function defined once. Both the prefill CTA (`onClick={() => void handleBind(prefillCode)`, line 457) and the typed-code auto-submit (`handleCodeDigit`, line 181-183 which calls `handleBind`) route through the same `bindDevice({ code })` API call at line 128. Single call site verified. |
| T-08-QR-SC | Tampering | mitigate | CLOSED | `frontend/package.json:22` — `"react-qr-code": "^2.0.21"`. `frontend/package-lock.json:3421` — resolved version is `2.0.21`, resolved from `react-qr-code-2.0.21.tgz`. License: MIT. No `scripts.postinstall` field in the package-lock entry for `node_modules/react-qr-code` (only `dependencies`: `prop-types`, `qr.js`). Note: `^2.0.21` is a range specifier, not an exact pin — allows patch bumps within 2.x. The lockfile pins the resolved version to exactly `2.0.21`; the lockfile is the operative artifact for reproducible installs. |

### Plan 08-03 — Recently-Pulled / Reset / Idle (Frontend)

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-08-PR-01 | Information Disclosure | mitigate | CLOSED | `frontend/src/state/recentlyPulledStore.ts:59,61` — `name: 'gruvax-kiosk-recent'` and `storage: createJSONStorage(() => sessionStorage)`. The key is distinct from `gruvax-admin` (localStorage). `persist` middleware writes only to `sessionStorage`. Physical confirmation (hard Chromium restart clears chips) deferred to 08-HUMAN-UAT.md. |
| T-08-PR-02 | Information Disclosure | mitigate | CLOSED | `frontend/src/routes/kiosk/KioskView.tsx:97-100` — `useIdleTimer(15 * 60 * 1000, () => { clearSearch(); useRecentlyPulledStore.getState().clear() })`. Hook fires after 15 minutes of no `pointermove`, `pointerdown`, `keydown`, or `touchstart` events (`frontend/src/hooks/useIdleTimer.ts:20,33-37`). Clears both search state and recently-pulled strip. |
| T-08-PR-03 | Elevation of Privilege | mitigate | CLOSED | `frontend/src/routes/kiosk/KioskView.tsx:89-93` — `handleReset` calls only `clearSearch()`, `useRecentlyPulledStore.getState().clear()`, and `setShowResetConfirm(false)`. No `fetch`, `axios`, or network call present. `frontend/src/routes/kiosk/ResetConfirmDialog.tsx` — component receives `onConfirm`/`onCancel` callbacks only; no API calls, no imports of fetch/axios/api modules. Physical confirmation (Network tab zero calls) deferred to 08-HUMAN-UAT.md. |
| T-08-PR-04 | Spoofing | mitigate | CLOSED | `frontend/src/routes/kiosk/KioskView.tsx:52,751-762` — `const isLoggedIn = useAdminStore((s) => s.isLoggedIn)` reads per-browser in-memory Zustand store; the Reset button is conditionally rendered as `{!isLoggedIn && (<button ...>RESET KIOSK</button>)}`. Visibility is driven entirely by local client state, not a server-returned flag. |

---

## Unregistered Flags

None. The SUMMARY.md `## Threat Flags` sections for both 08-02 and 08-03 report "None" — all new attack surface was pre-mapped to existing threat IDs.

---

## Accepted Risks Log

None. All threats in this phase carry `mitigate` disposition; no threats were accepted or transferred.

---

## Human UAT Pending

The following code-level mitigations are fully present in the static implementation. Physical confirmation steps requiring a running kiosk session are deferred to `08-HUMAN-UAT.md`:

- T-08-QR-02: Confirm stale QR code yields mapBindError error message on physical phone scan.
- T-08-QR-03: Confirm no network call fires when prefill screen mounts (DevTools Network tab).
- T-08-QR-04: Confirm PinOverlay blocks the /admin/devices route when scanned while logged out.
- T-08-PR-01: Confirm recently-pulled chips are absent after hard Chromium restart (quit + relaunch).
- T-08-PR-03: Confirm Reset Kiosk produces zero Network tab entries on confirm.

These physical steps do not affect the SECURED verdict — the code-level mitigations are statically verified as present.

---

## Notes

**T-08-QR-SC package pin:** `package.json` uses `^2.0.21` (semver range), not an exact pin. The `package-lock.json` resolves this to exactly `2.0.21` and is the operative artifact for `npm ci` installs. In practice this is functionally equivalent to an exact pin for CI, but a future `npm install` on a new version bump within `^2.x` would update the lockfile. Flagged for awareness; not a blocker at L1 for a home-LAN application.

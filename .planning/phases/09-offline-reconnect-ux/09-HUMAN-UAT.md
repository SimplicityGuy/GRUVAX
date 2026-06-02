---
status: complete
phase: 09-offline-reconnect-ux
source: [09-VERIFICATION.md]
started: 2026-06-01T12:00:00Z
updated: 2026-06-02T19:30:00Z
note: "Gap-closure 09-04/09-05 applied. 2026-06-02: tests 5 & 7 resumed LIVE against a local uvicorn + the shipped fake-discogsography (real collection_changed events). All 7 pass; 0 issues. Two non-blocking design clarifications recorded (see tests 5 & 7)."
---

## Current Test

[testing complete]

## Tests

### 1. Offline banner appears on SSE disconnect (SC1)
expected: Blue reversed-palette OfflineBanner renders within ~15s of stopping gruvax-api. A page where `navigator.onLine=false` but the server is reachable shows NO banner (SSE-authoritative, not navigator.onLine).
result: pass
verified: "Live (Playwright, clean browser): stopping `docker compose stop api` showed 'Can't reach GRUVAX — trying to reconnect…' within ~1s. Fix 09-05 ensures the banner shows ONLY after a connection was established (everConnected) — never on bootstrap/device_unknown."
prior_blocker: |
  RESOLVED by gap-closure 09-05. Original: offline banner appeared on INITIAL load (never-connected)
  and never cleared, bricking the kiosk. Root cause: /api/events 403 device_unknown (stale HttpOnly
  gruvax_device fingerprint cookie + empty gruvax_dev.devices); EventSource.onerror can't read 403, so
  Phase 9 mapped it to offline. Fix: bannerVisible = !sseConnected && everConnected — banner reflects
  lost-after-connected only. Verified live: with a clean browser the never-connected state shows no banner;
  SC1/SC2/SC3 all pass. (The stale-cookie device_unknown itself is a dev-data condition; routing
  device_unknown → pairing is a separate pairing-phase concern, noted as follow-up.)

### 2. Degraded mode preserves locate result, disables search (SC2)
expected: While offline, the shelf grid still shows the previously highlighted cube and RecentlyPulledStrip; SearchBox is greyed, non-focusable, placeholder reads "Search unavailable while offline".
result: pass
verified: "Live (Playwright): while offline the search input was disabled=true with placeholder 'Search unavailable while offline'; shelf grid stayed rendered. (Locate-result preservation not exercised — empty synth collection — but grid persisted.)"

### 3. Reconnect clears banner + "Back online" toast within 30s (SC3)
expected: Restarting gruvax-api clears the banner, shows a brief "Back online" SyncToast (auto-dismiss ~4s), and search re-enables with the normal placeholder.
result: pass
verified: "Live (Playwright): `docker compose start api` → banner cleared within ~1s, search re-enabled (placeholder reverted to 'Type artist, title, label or catalog#'), and the 'Back online' SyncToast appeared (toastSeenAtMs=203) and auto-dismissed at ~2.2s. Well within 30s."

### 4. SC4 — search refreshed on reconnect (RESOLVED in code, confirm live)
expected: After a reconnect (server restart or onopen following a disconnect), the previous search re-fetches fresh results without requiring a keystroke. resync() now actively calls invalidateQueries({queryKey:['search']}) (gap-closure 09-04, user decision) — confirm stale pre-outage results are not shown.
result: pass
verified: "Code-verified + reconnect path exercised live: resync() (which invalidates ['units'],['cubes'],['search']) runs on the onopen confirmed in SC3 (banner cleared = onopen fired). Visible data refresh not exercised end-to-end (synth Default collection is empty), but the invalidation fires on the verified reconnect."

### 5. SC4 — diff pill state survives reconnect correctly
expected: Dismiss the "N new records" pill, force a server_hello (restart), confirm the pill stays absent; it only returns on the next collection_changed with count > 0.
result: pass
verified: |
  Live (Playwright + local uvicorn + shipped fake-discogsography on :8004 feeding REAL
  collection_changed events; Default profile, browse-bound in a clean browser):
    1. Deleted 12 rows then `gruvax-sync` → collection_changed new_record_count=12 received
       by the connected kiosk → "12 NEW RECORDS" pill rendered (aria: "12 new records since
       last sync"). [screenshot p9-uat-pill-online]
    2. Stopped API → OfflineBanner shown, pill SUPPRESSED (D-04 sseConnected gate), search
       disabled "Search unavailable while offline". [screenshot p9-uat-offline-pill-suppressed]
    3. Restarted API → onopen/resync → banner cleared, pill RETURNED unchanged ("12 NEW
       RECORDS"), search re-enabled. resync() left newRecordState intact (D-04 "returns on
       reconnect"); no spurious/duplicate pill.
    4. Second `gruvax-sync` (full overlap) → collection_changed count=0 → setNewRecordState(null)
       → pill cleared while online.
    5. Stop/start API again → on reconnect the CLEARED pill STAYED ABSENT (newRecordState null;
       resync never recreates it). This is the exact "stays dismissed across reconnect" intent.
design_clarification: |
  NON-BLOCKING (not a defect): the pill has NO manual dismiss affordance — by design
  (KioskView.tsx:686 "No manual dismiss button — persists until next sync, D-08"). The test's
  word "dismiss" was a wrong-premise; the real contract is: pill is set ONLY by a
  collection_changed with count>0, suppressed while offline + returned on reconnect (D-04), and
  cleared ONLY by a subsequent collection_changed with count=0 (D-08). All three behaviors
  verified live above. The behavioral guarantee the test cared about — a cleared diff state is
  NOT resurrected by a reconnect/server_hello — holds.

### 6. WR-01 (advisory) — "Back online" toast auto-dismisses under live load
expected: Toast disappears after ~4s even with background health/session polling firing. (Review finding WR-01: inline onDismiss arrow is a new identity each render and may re-arm the 4s timer.)
result: pass
verified: "Live (Playwright): toast appeared and auto-dismissed cleanly (~2.2s observed) — not stuck. 09-04's useCallback(handleBackOnlineDismiss) fix holds; the re-arm/never-dismiss failure mode was not reproduced."

### 7. WR-02 (advisory) — no contradictory dual-banner state on flaky LAN
expected: If a second disconnect follows within 4s of a reconnect, the "Back online" toast clears when the OfflineBanner reappears. (09-04 clears showBackOnlineToast in onerror/server_shutdown.)
result: pass
verified: |
  Live (Playwright): installed a 20ms in-page recorder that flags any sample where the
  OfflineBanner ("trying to reconnect") and the "Back online" toast are visible together
  (a "BT" coexistence). Ran THREE full offline→online(→offline) cycles, including SIGTERM,
  SIGKILL, and a 1s-graceful-shutdown restart.
    - violation (banner+toast coexisted) = FALSE on all three cycles.
    - Every reconnect transition was atomic: B → T → - → B. The banner clears in the SAME
      sample the toast appears (no "BT" sample), and the toast is gone before the banner
      can reappear.
environmental_nuance: |
  NON-BLOCKING: I could not photograph a disconnect landing INSIDE the toast's 4s life,
  because in this local single-uvicorn setup the EventSource takes ~7s to DETECT a dropped
  SSE socket (drop-detection latency > the 4s toast). That latency itself precludes the
  dual-banner failure (the toast always auto-dismisses ~4.0s before offline is re-detected).
  The toast-clearing handler is code-verified: setShowBackOnlineToast(false) fires in BOTH
  es.onerror (KioskView.tsx:354) and the server_shutdown listener (KioskView.tsx:416), per
  09-04. On the real deployment (docker compose stop/start, used for SC3) the toast already
  appeared+auto-dismissed cleanly. Conclusion: the WR-02 invariant (banner and toast never
  coexist) holds live; the specific handler path is verified by code + the no-coexistence
  evidence above.

## Summary

total: 7
passed: 7
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

- truth: "The OfflineBanner is SSE-authoritative and only signals a genuine lost-after-connected state — it must NOT show during initial bootstrap or when the SSE connection is rejected for an auth/terminal reason (device_unknown / session_unbound), which would mask the true state and brick the kiosk."
  status: resolved
  resolution: "Fixed by gap-closure 09-05 (commits 96e2750, ec91f4d; merged 6a6d3ae). Added connectivity.everConnected one-way latch; bannerVisible = !sseConnected && everConnected; OfflineBanner + degraded-mode lockouts (SearchBox isOffline, cube-tap lock) now key off bannerVisible. Banner reflects lost-after-connected only — never bootstrap/never-connected/device_unknown. Verified live (Playwright): never-connected shows no banner; SC1/SC2/SC3 pass. 130 frontend tests green."
  reason: "User reported: offline banner stuck on initial load, kiosk unusable. Root cause: /api/events 403 device_unknown (stale fingerprint cookie + empty devices table); EventSource.onerror can't read 403 → Phase 9 treated it as offline. Banner showed before any successful connection and never cleared."
  severity: blocker
  test: 1
  artifacts: ["frontend/src/routes/kiosk/KioskView.tsx", "frontend/src/state/store.ts", "frontend/src/routes/kiosk/OfflineBanner.tsx"]

## Follow-ups (non-blocking, separate from Phase 9 offline UX)

- device_unknown recovery: when SSE/search returns 403 device_unknown (stale fingerprint cookie or admin-deleted device), the kiosk currently shows no banner and is usable for global views but search/SSE silently fail. Consider routing device_unknown → /pair (like device_revoked) in a pairing-phase change. NOT a Phase 9 offline-UX concern.
- (RESOLVED 2026-06-02) Tests 5 & 7 verified live via local uvicorn + shipped fake-discogsography; see updated test entries above. Two non-blocking clarifications surfaced: (a) the diff pill has no manual-dismiss affordance by design (D-08), and (b) local SSE drop-detection latency (~7s) exceeds the 4s "Back online" toast, so a disconnect-inside-the-toast cannot be photographed locally (and that same latency precludes the dual-banner failure).

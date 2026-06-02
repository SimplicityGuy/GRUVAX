---
status: testing
phase: 09-offline-reconnect-ux
source: [09-VERIFICATION.md]
started: 2026-06-01T12:00:00Z
updated: 2026-06-02T00:00:00Z
note: "Gap-closure 09-04 applied — SC4 search now actively invalidated on reconnect; WR-01/WR-02 fixed. Items 4/6/7 below are now 'confirm the fix works live' rather than open decisions."
---

## Current Test

number: 1
name: Offline banner appears on SSE disconnect (SC1)
expected: |
  Stop gruvax-api. Within ~15s a blue reversed-palette OfflineBanner appears on the kiosk.
  Setting navigator.onLine=false while the server is reachable does NOT trigger it.
awaiting: user response

## Tests

### 1. Offline banner appears on SSE disconnect (SC1)
expected: Blue reversed-palette OfflineBanner renders within ~15s of stopping gruvax-api. A page where `navigator.onLine=false` but the server is reachable shows NO banner (SSE-authoritative, not navigator.onLine).
result: issue
reported: "Offline banner ('Can't reach GRUVAX — trying to reconnect…') appears on INITIAL load (before stopping anything) and never clears — kiosk permanently bricked into degraded mode while the server is fully reachable."
severity: blocker
root_cause: |
  /api/events/{profile_id} returns 403 device_unknown. Device resolution (deps.py:201-231)
  prefers the HttpOnly gruvax_device fingerprint cookie over browse-binding; the browser carries
  a stale fingerprint cookie from earlier pairing tests, but gruvax_dev.devices is empty →
  device_unknown. EventSource.onerror cannot read the 403 status, so Phase 9 maps it to
  setSseConnected(false) → offline banner shows and never clears (onopen never fires).
  Backend verified healthy; SSE connects via curl with browse-binding only (retry: 3347).
  Two layers: (a) immediate trigger is stale dev-browser fingerprint cookie + empty devices table;
  (b) real gap — offline banner masks a never-established / device_unknown SSE state instead of
  routing to pairing (device_revoked is handled; device_unknown and never-connected are not).

### 2. Degraded mode preserves locate result, disables search (SC2)
expected: While offline, the shelf grid still shows the previously highlighted cube and RecentlyPulledStrip; SearchBox is greyed, non-focusable, placeholder reads "Search unavailable while offline".
result: [pending]

### 3. Reconnect clears banner + "Back online" toast within 30s (SC3)
expected: Restarting gruvax-api clears the banner, shows a brief "Back online" SyncToast (auto-dismiss ~4s), and search re-enables with the normal placeholder.
result: [pending]

### 4. SC4 — search refreshed on reconnect (RESOLVED in code, confirm live)
expected: After a reconnect (server restart or onopen following a disconnect), the previous search re-fetches fresh results without requiring a keystroke. resync() now actively calls invalidateQueries({queryKey:['search']}) (gap-closure 09-04, user decision) — confirm stale pre-outage results are not shown.
result: [pending]

### 5. SC4 — dismissed diff badge stays dismissed across reconnect
expected: Dismiss the "N new records" pill, force a server_hello (restart), confirm the pill stays absent; it only returns on the next collection_changed with count > 0.
result: [pending]

### 6. WR-01 (advisory) — "Back online" toast auto-dismisses under live load
expected: Toast disappears after ~4s even with background health/session polling firing. (Review finding WR-01: inline onDismiss arrow is a new identity each render and may re-arm the 4s timer.)
result: [pending]

### 7. WR-02 (advisory) — no contradictory dual-banner state on flaky LAN
expected: If a second disconnect follows within 4s of a reconnect, the "Back online" toast clears when the OfflineBanner reappears. (Current code does not clear showBackOnlineToast in onerror/server_shutdown.)
result: [pending]

## Summary

total: 7
passed: 0
issues: 1
pending: 6
skipped: 0
blocked: 0

## Gaps

- truth: "The OfflineBanner is SSE-authoritative and only signals a genuine lost-after-connected state — it must NOT show during initial bootstrap or when the SSE connection is rejected for an auth/terminal reason (device_unknown / session_unbound), which would mask the true state and brick the kiosk."
  status: failed
  reason: "User reported: offline banner stuck on initial load, kiosk unusable. Root cause: /api/events 403 device_unknown (stale fingerprint cookie + empty devices table); EventSource.onerror can't read 403 → Phase 9 treats it as offline. Banner shows before any successful connection and never clears."
  severity: blocker
  test: 1
  artifacts: ["frontend/src/routes/kiosk/KioskView.tsx", "frontend/src/state/store.ts", "src/gruvax/api/deps.py"]
  missing: ["distinguish never-connected from was-connected-then-dropped before showing banner", "handle device_unknown on SSE like device_revoked (route to /pair) instead of masking as offline"]

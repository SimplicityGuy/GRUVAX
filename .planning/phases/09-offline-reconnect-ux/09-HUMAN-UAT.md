---
status: partial
phase: 09-offline-reconnect-ux
source: [09-VERIFICATION.md]
started: 2026-06-01T12:00:00Z
updated: 2026-06-01T12:30:00Z
note: "Gap-closure 09-04 applied — SC4 search now actively invalidated on reconnect; WR-01/WR-02 fixed. Items 4/6/7 below are now 'confirm the fix works live' rather than open decisions."
---

## Current Test

[awaiting human testing]

## Tests

### 1. Offline banner appears on SSE disconnect (SC1)
expected: Blue reversed-palette OfflineBanner renders within ~15s of stopping gruvax-api. A page where `navigator.onLine=false` but the server is reachable shows NO banner (SSE-authoritative, not navigator.onLine).
result: [pending]

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
issues: 0
pending: 7
skipped: 0
blocked: 0

## Gaps

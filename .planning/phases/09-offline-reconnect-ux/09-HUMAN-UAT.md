---
status: partial
phase: 09-offline-reconnect-ux
source: [09-VERIFICATION.md]
started: 2026-06-01T12:00:00Z
updated: 2026-06-02T18:42:00Z
note: "Gap-closure 09-04 applied — SC4 search now actively invalidated on reconnect; WR-01/WR-02 fixed. Items 4/6/7 below are now 'confirm the fix works live' rather than open decisions."
---

## Current Test

[SC1, SC2, SC3 verified live after 09-05 fix. Tests 5 & 7 pending a non-empty collection / flaky-LAN stress pass.]

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

### 5. SC4 — dismissed diff badge stays dismissed across reconnect
expected: Dismiss the "N new records" pill, force a server_hello (restart), confirm the pill stays absent; it only returns on the next collection_changed with count > 0.
result: [pending]
note: "Not exercised — requires a collection_changed event (non-empty diff) to surface the pill first. Code: resync() does not touch newRecordState, so a dismissed pill is not re-shown on reconnect. Recommend confirming once a real synced collection with a diff is available."

### 6. WR-01 (advisory) — "Back online" toast auto-dismisses under live load
expected: Toast disappears after ~4s even with background health/session polling firing. (Review finding WR-01: inline onDismiss arrow is a new identity each render and may re-arm the 4s timer.)
result: pass
verified: "Live (Playwright): toast appeared and auto-dismissed cleanly (~2.2s observed) — not stuck. 09-04's useCallback(handleBackOnlineDismiss) fix holds; the re-arm/never-dismiss failure mode was not reproduced."

### 7. WR-02 (advisory) — no contradictory dual-banner state on flaky LAN
expected: If a second disconnect follows within 4s of a reconnect, the "Back online" toast clears when the OfflineBanner reappears. (09-04 clears showBackOnlineToast in onerror/server_shutdown.)
result: [pending]
note: "Not stress-tested. Observed in SC3 that the toast appears as the banner clears (not simultaneously with an offline banner). 09-04 adds setShowBackOnlineToast(false) to es.onerror + server_shutdown. Recommend a rapid disconnect-within-4s-of-reconnect stress check on the real flaky LAN."

## Summary

total: 7
passed: 5
issues: 0
pending: 2
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
- Tests 5 & 7 (diff-badge-stays-dismissed, rapid flaky-LAN dual-banner) need a non-empty synced collection / rapid-cycle stress and remain pending for a later live pass.

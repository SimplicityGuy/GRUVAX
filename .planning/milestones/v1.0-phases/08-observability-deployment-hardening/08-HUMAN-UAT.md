---
status: complete
phase: 08-observability-deployment-hardening
source: [08-VERIFICATION.md]
started: 2026-05-25
updated: 2026-05-26T00:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Admin Diagnostics page renders + behaves per UI-SPEC
expected: Sign in to admin (PIN 0000) and open `/admin/diagnostics`. All section cards render with Nordic Grid styling (typography limited to 24/18/16/14px, Barlow Condensed ALL-CAPS headings, DM Mono for numbers/timings, dark terminal for recent logs). The REFRESH button reloads data on demand with NO background polling/SSE. The RESET STATS inline-confirm flow works: "YES, RESET" clears TOP SEARCHED; "KEEP STATS" is a no-op.
result: pass

### 2. Kiosk staleness banner appears >14d, hides when fresh
expected: With `max(v_collection.synced_at)` forced > 14 days old, the kiosk shows a persistent yellow banner above the grid reading "Collection data may be outdated — last synced {N}d ago". Search still works at any staleness. The no-results page stays generic (NO staleness hint — D-02 descope). When sync is recent, the banner disappears.
result: pass
note: Verified 2026-05-26 by forcing `UPDATE gruvax_dev.collection_items SET updated_at = now() - interval '15 days';` (dev DB schema is `gruvax_dev`, not `discogsography`; column is `updated_at` per migration 0002 view aliasing `ci.updated_at AS synced_at`). Banner appeared, search still worked, no-results stayed generic, banner cleared after `UPDATE ... SET updated_at = now();` and the next 60s `_refresh_sync_age` tick.

## Summary

total: 2
passed: 2
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

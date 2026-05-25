---
status: partial
phase: 08-observability-deployment-hardening
source: [08-VERIFICATION.md]
started: 2026-05-25
updated: 2026-05-25
---

## Current Test

[awaiting human testing]

## Tests

### 1. Admin Diagnostics page renders + behaves per UI-SPEC
expected: Sign in to admin (PIN 0000) and open `/admin/diagnostics`. All section cards render with Nordic Grid styling (typography limited to 24/18/16/14px, Barlow Condensed ALL-CAPS headings, DM Mono for numbers/timings, dark terminal for recent logs). The REFRESH button reloads data on demand with NO background polling/SSE. The RESET STATS inline-confirm flow works: "YES, RESET" clears TOP SEARCHED; "KEEP STATS" is a no-op.
result: [pending]

### 2. Kiosk staleness banner appears >14d, hides when fresh
expected: With `max(v_collection.synced_at)` forced > 14 days old, the kiosk shows a persistent yellow banner above the grid reading "Collection data may be outdated — last synced {N}d ago". Search still works at any staleness. The no-results page stays generic (NO staleness hint — D-02 descope). When sync is recent, the banner disappears.
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps

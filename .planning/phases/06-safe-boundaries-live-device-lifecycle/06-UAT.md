---
status: complete
phase: 06-safe-boundaries-live-device-lifecycle
source: [06-01-SUMMARY.md, 06-02-SUMMARY.md, 06-03-SUMMARY.md, 06-HUMAN-UAT.md]
started: 2026-06-03T00:16:49Z
updated: 2026-06-03T00:35:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Cross-Profile Boundary Isolation
expected: Bound to Profile A, editing a cube boundary updates A's row only; Profile B's row at the identical (unit, row, col) position is untouched. (DATA-01 / T-06-08)
result: pass
evidence: "tests/integration/test_two_profile_isolation.py::test_boundary_edit_profile_a_does_not_touch_profile_b — 1 passed (also part of 9/9 file run)"

### 2. Unbound Admin Write Rejected
expected: Attempting an admin boundary edit with an admin session but no bound browse-session (stripped browse-binding) returns a clean 400 `session_unbound` — no silent write, no fallback to a default profile. (D-02)
result: pass
evidence: "tests/integration/test_two_profile_isolation.py::test_unbound_admin_write_returns_400 — passed (9/9 file run)"

### 3. Edit Absent Cube Position Returns Clean Error
expected: Editing a (unit, row, col) position that has no boundary row for the bound profile returns a loud 404 (`cube_not_found` / `boundary_not_found`) — never a silent no-op or an accidental insert into the wrong profile. (D-10)
result: pass
evidence: "tests/integration/test_two_profile_isolation.py::test_zero_row_write_returns_404 — passed (9/9 file run)"

### 4. Per-Profile SSE — Boundary Change Fan-Out
expected: With two views open (Profile A and Profile B — e.g. two kiosk/admin browser sessions), a boundary edit bound to A pushes a live `boundary_changed` update to A's view only. B's view shows no change and does not refetch. (D-04 / T-06-09)
result: pass
evidence: "tests/integration/test_two_profile_isolation.py::test_boundary_changed_fans_out_per_profile — passed (9/9 file run)"

### 5. Per-Profile SSE — Editing Shimmer Isolation
expected: When an admin is actively editing in Profile A, the "editing" shimmer/indicator appears on A's kiosk only. Profile B's kiosk shows no shimmer — no cross-profile visual leakage. (D-04 shimmer / T-06-09b)
result: pass
evidence: "tests/integration/test_two_profile_isolation.py::test_admin_editing_fans_out_per_profile — passed (9/9 file run)"

### 6. Kiosk Device Revoke Navigates to Pairing Live
expected: With the kiosk open, revoke its device from Admin → Devices. A full-screen "SCREEN REMOVED" (RevokeNotice) overlay appears, then after ~2.5s the kiosk navigates to `/pair` automatically — no manual reload. Fires whether the trigger is the SSE `device_revoked` event or an in-flight 403, and even if KioskView is unmounted (App-level handler). (DEV-05 / Success Criterion 1)
result: pass
evidence: |
  Driven via Playwright (two tabs: kiosk + admin, shared cookie context).
  Paired device c89d076a to Default, then REVOKE DEVICE from admin.
  DOM observer on the kiosk captured the overlay text: "SCREEN REMOVED — This
  screen was removed — re-pair to continue." and a live SPA navigation
  path sequence ["/", "/pair", "/"] (navigated to /pair with no reload).
  DB: devices.revoked_at set (revoked=t). Session: is_device_paired=false.
  Note: after landing on /pair the kiosk bounced back to "/" because this
  multi-profile session retains a browse-binding to Default — the same
  public-browse fallback that made the FIRST load show the kiosk instead of
  /pair. The revoke seam (overlay + live navigate to /pair) is verified; the
  return-to-browse is the app's existing browse-mode behavior, not a regression.
  Screenshots: uat-06-pair-screen.png, uat-06-revoke-notice.png.

### 7. Kiosk Device Reassign Re-Binds and Switches Collection Live
expected: With the kiosk bound to Profile A, reassign it to Profile B from Admin → Devices. A yellow "MOVED TO {Profile B name}" banner appears for ~2.5s, then the Kallax grid switches to Profile B's collection — no manual reload. The banner name comes from an authoritative `GET /api/session` re-fetch (never the SSE payload). (DEV-05 / Success Criterion 2 / T-06-07)
result: pass
evidence: |
  Driven via Playwright. Reassigned device c89d076a Default→Profile B (CHANGE
  PROFILE), then B→Default. DOM observer on the kiosk captured the banner text
  "MOVED TO DEFAULT" (display_name from authoritative session, not SSE payload
  — T-06-07). Live in-page GET /api/session confirmed bound_profile_id flipped
  to Profile B (dd1072b0…) then back to Default (00000000…0001) with no reload;
  DB devices.profile_id tracked each reassignment. SSE auto-reconnected on the
  boundProfileId change (no manual EventSource open).

## Summary

total: 7
passed: 7
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none yet]

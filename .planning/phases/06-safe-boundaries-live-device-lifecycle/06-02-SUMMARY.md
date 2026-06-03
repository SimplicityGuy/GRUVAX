---
phase: "06-safe-boundaries-live-device-lifecycle"
plan: "02"
subsystem: "frontend-kiosk"
tags: ["sse", "device-lifecycle", "zustand", "tdd", "nordic-grid"]
dependency_graph:
  requires: []
  provides: ["device_revoked-handler", "device_reassigned-handler", "terminal-revoke-seam"]
  affects: ["frontend/src/state/sessionStore.ts", "frontend/src/api/client.ts", "frontend/src/App.tsx", "frontend/src/routes/kiosk/KioskView.tsx", "frontend/src/routes/kiosk/DeviceLifecycle.tsx"]
tech_stack:
  added: []
  patterns: ["idempotent-signal-store", "mount-independent-effect", "sse-lifecycle-handler"]
key_files:
  created:
    - "frontend/src/routes/kiosk/DeviceLifecycle.tsx"
    - "frontend/src/routes/kiosk/DeviceLifecycle.css"
    - "frontend/src/api/client.revoke.test.ts"
  modified:
    - "frontend/src/state/sessionStore.ts"
    - "frontend/src/api/client.ts"
    - "frontend/src/App.tsx"
    - "frontend/src/routes/kiosk/KioskView.tsx"
    - "frontend/src/routes/kiosk/KioskView.EventSource.test.tsx"
decisions:
  - "App.tsx is the single terminal-revoke handler (not KioskView) — fires even when KioskView is unmounted (D-06)"
  - "triggerRevoke() is idempotent — SSE + 403 race resolves to one notice, one navigation"
  - "device_reassigned reads profile name from authoritative GET /api/session re-fetch, never from SSE payload (T-06-07)"
  - "SSE reconnect after reassign is automatic — setSession updates boundProfileId which is in the effect dep array"
metrics:
  duration: "~12m"
  completed: "2026-05-31"
  tasks_completed: 2
  files_changed: 9
requirements-completed: [DEV-05]
---

# Phase 6 Plan 2: Device Lifecycle SSE Handlers + Terminal-Revoke Seam Summary

Wired the kiosk SSE consumer to react live to `device_revoked` and `device_reassigned` events, closing DEV-05 (kiosk consumer side). Delivered a mount-independent terminal-revoke seam: both the SSE event and any in-flight 403 `device_revoked` response route through a single idempotent `triggerRevoke()` signal consumed by App.tsx — the kiosk exits exactly once regardless of which signal arrives first and regardless of whether KioskView is mounted.

## What Was Built

### Task 1 — Lifecycle UI state + unified terminal-revoke handler

**sessionStore.ts** gained four new fields/actions:
- `revokePending: boolean` — set by `triggerRevoke()` (idempotent, second call is no-op)
- `triggerRevoke()` — sets `revokePending: true` only if currently false
- `resetRevoke()` — clears after navigate('/pair') so a future re-pair can revoke again
- `reassignBanner: string | null` + `setReassignBanner(name)` — drives "MOVED TO" banner

**client.ts** gained `check403Revoke()` — a shared response-check helper called by every fetch wrapper. When `res.status === 403` and `detail.type === 'device_revoked'`, it calls `useSessionStore.getState().triggerRevoke()` (mount-independent — no React subscription needed) then throws `Error('device_revoked')`.

**App.tsx** `AppInner` gained a `useEffect` subscribed to `revokePending`. When true: renders `RevokeNotice` overlay, waits ~2.5s, then calls `clearBoundProfile()` (nulls `boundProfileId` → KioskView's SSE cleanup closes the old EventSource, D-07), navigates to `/pair`, and calls `resetRevoke()`. This is the **single terminal-revoke handler** — runs at App level, mount-independent of KioskView (D-06).

**DeviceLifecycle.tsx** (new) exports two Nordic-Grid-styled components:
- `RevokeNotice` — full-screen overlay (blue background, yellow icon, ALL-CAPS heading)
- `ReassignBanner` — top banner "MOVED TO {name}" (yellow background, auto-dismisses ~2.5s)

**DeviceLifecycle.css** (new) — all colors via CSS custom properties (zero hex literals, CLAUDE.md compliance).

### Task 2 — device_revoked + device_reassigned SSE handlers

**KioskView.tsx** SSE `useEffect` gained two new listeners:
- `device_revoked`: calls `useSessionStore.getState().triggerRevoke()` — no local teardown/navigation (App.tsx owns it, D-06)
- `device_reassigned`: calls `getSession()` → `setSession(data)` → derives `display_name` from the authoritative session response → `setReassignBanner(name)` + invalidates `['units']`, `['cubes']`, `['search']` keys; the `boundProfileId` dep change auto-reconnects SSE to the new channel (no manual EventSource open)

**KioskView.tsx** render section gains `<ReassignBanner />` from `DeviceLifecycle.tsx` above the ReauthBanner.

## Test Coverage

- `src/api/client.revoke.test.ts` (new) — 3 tests: 403+device_revoked sets `revokePending`; other 403 types do not; `triggerRevoke()` idempotent + `resetRevoke()` clears. Proves mount-independent 403 path.
- `src/routes/kiosk/KioskView.EventSource.test.tsx` — 2 new tests added (D-06, D-08): `device_revoked` SSE sets `revokePending`; `device_reassigned` SSE calls `getSession` + sets `reassignBanner`. Fixed `getSession` mock setup for existing B-02 test (session polling query now mocked by default).
- Full suite: 62/62 tests pass. tsc clean.

## Deviations from Plan

None — plan executed exactly as written.

## Threat Mitigations Applied

| Threat | Mitigation Delivered |
|--------|---------------------|
| T-06-05 (stale SSE after revoke/reassign) | `clearBoundProfile()` nulls `boundProfileId` → effect cleanup closes old `EventSource`; no second channel opened manually |
| T-06-06 (403 + SSE revoke race) | Both route through idempotent `triggerRevoke()`; single App.tsx effect; `revokePending` can only flip true once until `resetRevoke()` |
| T-06-07 (reassign banner leaking wrong profile name) | `display_name` derived from authoritative `GET /api/session` re-fetch; event payload (which carries only `device_id`) never used for the banner |

## Self-Check: PASSED

Files exist:
- `frontend/src/routes/kiosk/DeviceLifecycle.tsx` — FOUND
- `frontend/src/routes/kiosk/DeviceLifecycle.css` — FOUND
- `frontend/src/api/client.revoke.test.ts` — FOUND

Commits exist:
- `943f9ec` — test(06-02): RED test for 403 device_revoked path
- `3327ddc` — feat(06-02): lifecycle UI state + unified terminal-revoke handler (Task 1 GREEN)
- `c416e3a` — test(06-02): RED tests for device_revoked + device_reassigned SSE handlers
- `31b3e98` — feat(06-02): device_revoked + device_reassigned SSE handlers + ReassignBanner (Task 2 GREEN)

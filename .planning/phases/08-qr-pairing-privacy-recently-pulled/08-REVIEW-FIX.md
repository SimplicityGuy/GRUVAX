---
phase: 08-qr-pairing-privacy-recently-pulled
fixed_at: 2026-06-01T17:26:00Z
review_path: .planning/phases/08-qr-pairing-privacy-recently-pulled/08-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 6
skipped: 1
status: partial
---

# Phase 08: Code Review Fix Report

**Fixed at:** 2026-06-01
**Source review:** `.planning/phases/08-qr-pairing-privacy-recently-pulled/08-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope (Critical + Warning): 7
- Fixed: 6
- Skipped: 1 (false positive — see below)

## Fixed Issues

### CR-02: Hardcoded `#FFFFFF` hex in `admin.css`

**Files modified:** `frontend/src/routes/admin/admin.css`
**Commit:** `464b58a`
**Applied fix:** Replaced `#FFFFFF` with `var(--gruvax-white)` in three rules:
`.import-error-badge { color: #FFFFFF }`, `.import-suggestion-chip:hover { color: #FFFFFF }`,
and `.import-commit-btn--enabled { color: #FFFFFF }`.

---

### WR-02: `role="alert"` written as invalid CSS property

**Files modified:** `frontend/src/routes/admin/admin.css`
**Commit:** `e94e203`
**Applied fix:** Removed the dead `role: alert;` CSS declaration from the `.import-commit-error`
rule. The JSX element in `Import.tsx` already carries `role="alert"` correctly (confirmed at
line 714 — no JSX change needed).

---

### WR-03: `role="listitem"` on `<button>` in `RecentlyPulledStrip`

**Files modified:** `frontend/src/routes/kiosk/RecentlyPulledStrip.tsx`
**Commit:** `860bc4a`
**Applied fix:** Wrapped each chip `<button>` in `<div key={item.release_id} role="listitem">`.
Removed `role="listitem"` from the `<button>` element; all other button attributes (type,
className, aria-label, onClick) remain intact. The parent `<div>` keeps `role="list"`.
All 90 tests pass including KioskView and PairView test files.

---

### CR-01 + WR-05: Stale closures in `PairView.tsx`

**Files modified:** `frontend/src/routes/kiosk/PairView.tsx`
**Commits:** `ee9e17f`, `2644843`
**Applied fix:**

CR-01: Added `pairStatusRef = useRef<PairStatus>('loading')` and `updatePairStatus` callback
(stable via `useCallback([])`). The countdown `setInterval` now reads `pairStatusRef.current`
instead of the stale captured `pairStatus`. All `setPairStatus(...)` calls replaced with
`updatePairStatus(...)`. Added `updatePairStatus` to the countdown effect's dependency array
(which eliminated the previously-needed `eslint-disable-next-line` suppression comment there).

WR-05: Added `isFetchingRef = useRef(false)`. `fetchNewCode` now guards with
`isFetchingRef.current` (always current) instead of the stale captured `isCodeFetching`.
The ref is set `true` on entry and `false` in `finally`. The `useCallback` empty-deps array
remains safe — ESLint no longer flags it, so its `eslint-disable` comment was also removed.

All 6 PairView tests pass.

Note: `handlePaired` was also updated to use `updatePairStatus` for consistency; its
`useCallback` deps updated to include `updatePairStatus`.

---

### WR-04: `last_pairing_code` cast — comment-only fix

**Files modified:** `frontend/src/routes/admin/DeviceDrawer.tsx`
**Commit:** `c3a77a1`
**Applied fix:** Added a clarifying comment above the `last_pairing_code` cast noting that
the backend does not currently return this field, so `pendingCode` will always be `undefined`
and the fast-path branch is presently inert. The code falls through to `'bind-code'` mode as
designed. No behavior was changed; the branch is preserved for the planned bind-to-profile
API extension.

---

## Skipped Issues

### WR-01: `removeEventListener` options mismatch in `useIdleTimer.ts`

**File:** `frontend/src/hooks/useIdleTimer.ts:51`
**Reason:** skipped — false positive per orchestrator directive
**Original issue:** Reviewer flagged that `addEventListener` uses `{ passive: true }` while
`removeEventListener` omits the options object, suggesting the listener may not be removed.
Per the orchestrator analysis: the Web spec says `removeEventListener` matching considers only
the `capture` flag (not `passive`). The listener IS removed correctly because the same `reset`
function reference is used and both calls default to `capture: false`. No ghost listener is
left behind. Do NOT apply this change.

---

## Post-fix Verification

All three commands run from project root after the fast-forward merge:

**Lint:** `npm --prefix frontend run lint`
- Result: 0 errors, 1 warning (pre-existing in `BinWidthEditor.tsx` — unrelated to Phase 8)

**Build:** `npm --prefix frontend run build`
- Result: build succeeded in ~331ms, 0 errors (chunk size advisory is pre-existing)

**Tests:** `npm --prefix frontend run test -- --run`
- Result: **15 test files, 90 tests — all passing**

---

_Fixed: 2026-06-01_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_

---
phase: 02-multi-profile-migration-profile-manager
reviewed: 2026-05-28T00:00:00Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - frontend/src/routes/admin/ProfileDrawer.tsx
  - frontend/src/routes/admin/ProfileDrawer.test.tsx
  - src/gruvax/api/admin/profile_sync.py
  - frontend/src/state/store.ts
  - frontend/src/routes/kiosk/ShelfLayoutNotConfigured.tsx
  - frontend/src/routes/kiosk/ShelfLayoutNotConfigured.test.tsx
  - frontend/src/routes/kiosk/KioskView.tsx
  - frontend/src/routes/kiosk/kiosk.css
  - frontend/src/routes/kiosk/ResultsList.tsx
  - frontend/src/routes/kiosk/ResultsList.test.tsx
findings:
  critical: 0
  warning: 4
  info: 4
  total: 8
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-05-28
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Reviewed the two Phase-02 gap-closure plans: 02-08 (sync poll-until-terminal) and 02-09
(shelf-layout-not-configured affordance + ResultsList profile-id scoping fix). The diff is
small (10 files, ~662 insertions, mostly tests + documentation). The backend change
(`profile_sync.py`) is documentation-only — no behavioral change. The core fixes are sound:
the poll-until-terminal `refetchInterval` correctly continues through `null`/`in_progress`
and halts only on `'ok'`/`'failed'`, and `ResultsList` now passes the bound profile id on
both the auto-locate and explicit-select paths (matching `KioskView`'s relocate path).

No BLOCKER-class correctness, security, or data-loss defects were found in the diff.
Four WARNINGs concern a stale-closure / dependency gap in `ResultsList`, a silent-failure
fallback path, a dead comparison branch (`'completed'`) that the backend never emits, and
a poll-start race that the design tolerates but does not fully guard. Four INFO items cover
test-fixture inconsistencies and minor robustness/clarity issues.

## Warnings

### WR-01: ResultsList auto-locate effect omits `boundProfileId` from its dependency array

**File:** `frontend/src/routes/kiosk/ResultsList.tsx:66-88`
**Issue:** The auto-locate-top `useEffect` keys only on `topReleaseId` (line 88) and reads
`useSessionStore.getState().boundProfileId` at call-time (line 75). If the bound profile
changes while the same top result is still displayed (e.g. a switch-profile flow that does
not change the search results), the effect will NOT re-fire, so the previously-located cube
remains shown for the wrong profile until the next keystroke. The whole point of 02-09 was
to scope locate to the bound profile; this leaves a window where the displayed cube is
scoped to a stale profile. The explicit-select path (`handleSelect`, line 90-109) is fine
because it reads `getState()` on each tap, but the auto-locate path is the default path.
**Fix:** Re-run the auto-locate when the bound profile changes. Either add the bound id to
the effect deps:
```tsx
const boundProfileId = useSessionStore((s) => s.boundProfileId)
useEffect(() => {
  if (topReleaseId == null) return
  const top = items[0]
  setSelectedResult(top)
  setSelectedReleaseId(top.release_id)
  void locateRelease(top.release_id, boundProfileId ?? undefined)
    .then((result) => { setLocateResult(result); /* ... */ })
    .catch(() => setHighlightCube(null))
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [topReleaseId, boundProfileId])
```
or document explicitly that a profile switch always remounts KioskView (verify that is
actually true — `KioskView`'s SSE effect re-runs on `boundProfileId`, but this component is
not remounted by that).

### WR-02: locate without a bound profile silently fails (422 swallowed) leaving a blank shelf

**File:** `frontend/src/routes/kiosk/ResultsList.tsx:76, 98` (and `KioskView.tsx:216`)
**Issue:** `locateRelease(id, topPid ?? undefined)` is called with `undefined` when no
profile is bound. The backend declares `profile_id` as REQUIRED on `/api/locate`
(documented in the test header), so the call 422s and is swallowed by `.catch(() =>
setHighlightCube(null))`. The user gets no cube, no error, and no affordance — the exact
"swallowed 422" failure class 02-09 set out to eliminate, just relocated to the unbound
case. On the kiosk a profile is normally bound, but this path is reachable during bootstrap
or after an unbind race.
**Fix:** Guard the locate so it is not fired without a bound profile, and surface a state
rather than a blank shelf:
```tsx
const pid = useSessionStore.getState().boundProfileId
if (pid == null) { setHighlightCube(null); return }
void locateRelease(top.release_id, pid).then(/* ... */)
```

### WR-03: dead comparison — `last_sync_status !== 'completed'` is always true

**File:** `frontend/src/routes/kiosk/KioskView.tsx:463`
**Issue:** `isEmptyCollection` tests `boundProfile.last_sync_status !== 'completed'`, but the
backend never writes `'completed'`. Grepping `src/gruvax/` confirms the only emitted values
are `'ok'`, `'failed'`, `'in_progress'`, and `null` (`profile_sync.py`,
`sync/profile_sync.py`, `api/admin/profiles.py:91-92`). The `AdminProfile` type
(`types.ts:385`) types it as `'ok' | 'failed' | 'in_progress' | null` with no `'completed'`.
The branch is dead code that encodes a status the system does not produce, which is
misleading and risks masking a real status if the contract ever drifts. (Note: a test
fixture `KioskView.EventSource.test.tsx:125` *does* use `'completed'`, so the dead branch is
the only thing keeping that fixture meaningful — meaning the test asserts behavior on a
value the server never sends.)
**Fix:** Drop the `'completed'` comparison (and correct the comment on lines 456-457):
```tsx
const isEmptyCollection =
  boundProfile != null &&
  (boundProfile.last_sync_item_count == null || boundProfile.last_sync_item_count === 0) &&
  boundProfile.last_sync_status !== 'ok'
```
and update the `KioskView.EventSource.test.tsx` fixture to use a real status.

### WR-04: poll start can latch a stale terminal status before `in_progress` is observed

**File:** `frontend/src/routes/admin/ProfileDrawer.tsx:128-161, 248-261`
**Issue:** After SYNC NOW, the query enables (`connectState === 'syncing'`) and the first
GET may return the *previous* sync's terminal `'ok'` if it lands before the backend's
synchronous `in_progress` write is visible to that read. `refetchInterval` would then return
`false` (stop) and the terminal-handling effect would fire `'ok'` immediately —
mis-reporting "Sync complete" for a sync that never ran. The module docstring in
`profile_sync.py` argues the `in_progress` write happens synchronously before the 202
returns, and `handleSyncNow` awaits `syncAdminProfile` before flipping to `'syncing'`, which
makes this unlikely — but it relies on read-after-write visibility on a shared pool and is
not defended in code. The tests do not cover this ordering (they always mock `in_progress`
as the first tick).
**Fix:** Make the poll robust to a stale terminal on the first tick — e.g. require an
`in_progress` (or item-count progression) to have been observed before honoring a terminal
status, or have `handleSyncNow`/`handleConnect` optimistically seed the query cache with
`last_sync_status: 'in_progress'` so the first `refetchInterval` evaluation cannot read a
stale `'ok'`:
```tsx
queryClient.setQueryData(['admin','profiles', profileId],
  (prev: AdminProfile | undefined) => prev && { ...prev, last_sync_status: 'in_progress' })
setConnectState('syncing')
```

## Info

### IN-01: test fixture `TRANSIENT_NULL_TICK` is internally inconsistent

**File:** `frontend/src/routes/admin/ProfileDrawer.test.tsx:68-73`
**Issue:** The "transient null" tick sets `last_sync_status: null` but keeps
`status: 'connected'` and `last_sync_item_count: 3000` (inherited from `CONNECTED_PROFILE`).
A real transient window between the `in_progress` write and the terminal swap would not
carry a completed item count of 3000 with a null status. The assertion still passes because
the effect only branches on `last_sync_status`, but the fixture misrepresents the state it
claims to reproduce and could lull a future maintainer into trusting `last_sync_item_count`
during the null window.
**Fix:** Set `last_sync_item_count: null` (or the in-progress partial 1500) on
`TRANSIENT_NULL_TICK` to match a plausible real tick.

### IN-02: ResultsList test mock omits required `SearchResult` enum/shape parity check

**File:** `frontend/src/routes/kiosk/ResultsList.test.tsx:23-29`
**Issue:** The `locateRelease` mock returns a `LocateResult` missing `generated_at` and
`estimator_version`, which the real type / store consumers reference elsewhere
(`store.test.tsx` fixtures include them). The cast is implicit via the `vi.fn()` resolved
value, so a type drift in `LocateResult` would not be caught by this test. Low risk
(behavioral assertion is on the call args, not the result), but the fixture is not a
faithful `LocateResult`.
**Fix:** Include all required `LocateResult` fields in the mock resolved value, or type the
mock as `Partial<LocateResult>` intentionally with a comment.

### IN-03: `handleSyncCompleteStable` recreated when parent passes inline `onSyncComplete`

**File:** `frontend/src/routes/admin/ProfileDrawer.tsx:111-118, 142-161`
**Issue:** The terminal effect depends on `handleSyncCompleteStable`, which depends on
`onSyncComplete`. If the parent passes an inline arrow for `onSyncComplete`, the callback
identity changes on every parent render, re-running the terminal effect. The
`handledSyncStatusRef` guard (line 145) prevents duplicate side effects, so this is correct
today — but it is load-bearing and fragile. Worth a one-line comment that the ref guard is
what makes the unstable-parent-callback case safe, or have the parent memoize the callback.
**Fix:** Document the invariant at the effect, or `useCallback`-memoize `onSyncComplete` at
the call site (ProfileManager).

### IN-04: comment/code mismatch — `bannerVisible` typed as literal `false` but documented as a slice

**File:** `frontend/src/state/store.ts:20-24`
**Issue:** `ConnectivityState.bannerVisible: false` is a literal `false` type ("stub for the
deferred Offline-Banner slice; set false always this phase"). This is fine for a stub but
will require a type widening to `boolean` plus a setter when Plan 04 lands; the literal type
is easy to overlook. Not a defect, just a deferred-debt marker.
**Fix:** No action this phase; flag for Plan 04 to widen the type and add the setter.

---

_Reviewed: 2026-05-28_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

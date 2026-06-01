---
phase: 08-qr-pairing-privacy-recently-pulled
reviewed: 2026-06-01T00:00:00Z
depth: standard
files_reviewed: 20
files_reviewed_list:
  - frontend/package.json
  - frontend/src/hooks/useIdleTimer.ts
  - frontend/src/hooks/useIdleTimer.test.ts
  - frontend/src/routes/admin/DeviceDrawer.tsx
  - frontend/src/routes/admin/DeviceDrawer.test.tsx
  - frontend/src/routes/admin/DevicesManager.tsx
  - frontend/src/routes/admin/DevicesManager.test.tsx
  - frontend/src/routes/admin/admin.css
  - frontend/src/routes/kiosk/KioskView.tsx
  - frontend/src/routes/kiosk/KioskView.recentlyPulled.test.tsx
  - frontend/src/routes/kiosk/PairView.tsx
  - frontend/src/routes/kiosk/PairView.test.tsx
  - frontend/src/routes/kiosk/RecentlyPulledStrip.tsx
  - frontend/src/routes/kiosk/ResetConfirmDialog.tsx
  - frontend/src/routes/kiosk/ResetConfirmDialog.test.tsx
  - frontend/src/routes/kiosk/kiosk.css
  - frontend/src/routes/kiosk/pair.css
  - frontend/src/state/recentlyPulledStore.ts
  - frontend/src/state/recentlyPulledStore.test.ts
  - tests/integration/test_08_privacy.py
findings:
  critical: 2
  warning: 5
  info: 5
  total: 12
status: issues_found
---

# Phase 08: Code Review Report

**Reviewed:** 2026-06-01
**Depth:** standard
**Files Reviewed:** 20
**Status:** issues_found

## Summary

Phase 8 adds QR-code kiosk pairing (DEV-04), session-only recently-pulled chips (SRCH-09 / PRIV-01), a no-PIN client-side Reset, and an idle timer. The privacy invariants (PRIV-01/04) and the D-04 no-auto-submit gate are correctly implemented. The Reset and idle paths make zero API calls as required. The QR encodes only the 4-digit code in a bind URL — no PIN or PAT present.

Two blockers are identified: a stale-closure bug in `PairView.tsx` that causes `pairStatus` comparisons inside `setInterval` to read the initial render value instead of the current state (causing a missed `setPairStatus('expiring')` transition during some countdown windows), and three hardcoded `#FFFFFF` hex values in `admin.css` that violate the CI-enforced no-hardcoded-hex token constraint. Several warnings follow, including a `removeEventListener` options mismatch in `useIdleTimer`, an invalid CSS `role:` property in `admin.css`, an inaccessible `role="listitem"` on a `<button>` in `RecentlyPulledStrip`, and a `last_pairing_code` cast-to-undefined runtime risk in `DeviceDrawer`. The QR `bgColor`/`fgColor` prop usage with CSS variable strings is flagged as a compatibility note.

## Structural Findings (fallow)

No structural pre-pass was provided for this phase.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Stale closure — `pairStatus` read inside `setInterval` captures initial value

**File:** `frontend/src/routes/kiosk/PairView.tsx:158`
**Issue:** The countdown `setInterval` callback at line 141 references `pairStatus` (a React state variable captured in the closure when the effect runs). The effect dependency array at line 177 intentionally omits `pairStatus` (`// pairStatus is intentionally omitted`), so `pairStatus` inside the interval forever reads the value from the _first_ render where `pairingCode?.expires_at` changes (typically `'loading'` or `'active'`). This means the guard `pairStatus !== 'expired' && pairStatus !== 'paired'` at line 158 always evaluates against a stale value and can never correctly suppress the `setPairStatus('expiring')` call after those terminal states are reached. In practice:

- If `pairStatus` transitions to `'expired'` (due to the auto-reroll path on line 167), the interval still fires `setPairStatus('expiring')` on the next tick because it reads the stale `'active'` value rather than the current `'expired'` value.
- The re-entrant `rerollTriggeredRef.current` guard prevents a double-fetch, but the spurious `setPairStatus('expiring')` still causes a visible UI flicker back to the warning styling momentarily before the new code arrives.

**Fix:** Use a functional `setPairStatus` update or a `useRef` for the status check inside the interval. The cleanest pattern is to eliminate the guard entirely since `rerollTriggeredRef` already prevents double-rerolls, or to store the status in a ref alongside state:

```typescript
// Add alongside pairStatus state:
const pairStatusRef = useRef<PairStatus>('loading')
// After setPairStatus calls, sync the ref:
const updatePairStatus = (s: PairStatus) => {
  pairStatusRef.current = s
  setPairStatus(s)
}
// Then inside the interval, use pairStatusRef.current instead of pairStatus:
if (clamped <= 60_000 && pairStatusRef.current !== 'expired' && pairStatusRef.current !== 'paired') {
  updatePairStatus('expiring')
}
```

---

### CR-02: Hardcoded `#FFFFFF` hex in `admin.css` — violates CI token enforcement

**File:** `frontend/src/routes/admin/admin.css:4551,4615,4681`
**Issue:** Three rules use the literal `#FFFFFF` instead of the `--gruvax-white` design token. The project's CI grep enforces that no hardcoded hex appears in CSS files (CLAUDE.md constraint). These will fail the CI check:

- Line 4551: `.import-error-badge { color: #FFFFFF; }`
- Line 4615: `.import-suggestion-chip:hover { color: #FFFFFF; }`
- Line 4681: `.import-commit-btn--enabled { color: #FFFFFF; }`

This is a blocking CI failure, not merely a style preference.

**Fix:**
```css
/* Line 4551 */
.import-error-badge { color: var(--gruvax-white); }

/* Line 4615 */
.import-suggestion-chip:hover { color: var(--gruvax-white); }

/* Line 4681 */
.import-commit-btn--enabled { color: var(--gruvax-white); }
```

---

## Warnings

### WR-01: `removeEventListener` options mismatch may leave ghost listeners

**File:** `frontend/src/hooks/useIdleTimer.ts:51`
**Issue:** `addEventListener` is called with `{ passive: true }` (line 42), but `removeEventListener` is called without any options object (line 51). Per the Web spec, a listener registered with `{ passive: true }` is a distinct entry from one registered without options. On browsers that treat the `passive` flag as part of the listener identity (all modern browsers do), the `removeEventListener` call without `{ passive: true }` will silently fail to remove the listener, leaving a ghost event listener on `document` that calls the stale `reset` closure from the previous effect run. This can cause idle timer callbacks to fire unexpectedly after `timeoutMs` changes.

**Fix:**
```typescript
return () => {
  IDLE_EVENTS.forEach((event) =>
    document.removeEventListener(event, reset, { passive: true } as EventListenerOptions),
  )
  if (timerRef.current !== null) clearTimeout(timerRef.current)
}
```
Note: `removeEventListener` accepts `EventListenerOptions` (not `AddEventListenerOptions`), so cast accordingly if TypeScript complains.

---

### WR-02: `role="alert"` written as invalid CSS property in `admin.css`

**File:** `frontend/src/routes/admin/admin.css:4652`
**Issue:** Inside the `.import-commit-error` rule, the declaration `role: alert;` appears. `role` is an HTML attribute, not a CSS property. CSS parsers will silently ignore this line. This means the `.import-commit-error` element does not actually have `role="alert"` — it will not be announced by screen readers when it appears. Any component using this class for error display has a silent accessibility regression; the `role` must be applied in the JSX/HTML, not in CSS.

**Fix:** Remove `role: alert;` from the CSS rule. In the component that renders `.import-commit-error`, add `role="alert"` to the element directly:
```tsx
<p className="import-commit-error" role="alert">{error}</p>
```

---

### WR-03: `role="listitem"` on `<button>` in `RecentlyPulledStrip` is an invalid ARIA combination

**File:** `frontend/src/routes/kiosk/RecentlyPulledStrip.tsx:45`
**Issue:** Each chip is rendered as `<button role="listitem">`. The `listitem` role is only valid as a child of an element with `role="list"` or `role="listbox"`. The parent `<div>` at line 36 has `role="list"`. However, `<button>` has an implicit role of `button`, and the ARIA spec prohibits overriding interactive native roles with structural roles like `listitem`. Screen readers may ignore or misannounce these elements. The correct pattern is to wrap the button in a `<div role="listitem">` or use a `<ul>`/`<li>` structure.

**Fix:**
```tsx
<div role="list" aria-label="Recently pulled records" className="recently-pulled-strip__chips">
  {items.map((item) => (
    <div key={item.release_id} role="listitem">
      <button
        type="button"
        className="recently-pulled-chip"
        aria-label={chipLabel}
        onClick={() => setSelectedReleaseId(item.release_id)}
      >
        ...
      </button>
    </div>
  ))}
</div>
```

---

### WR-04: `last_pairing_code` type-cast to unknown field — silent undefined at runtime

**File:** `frontend/src/routes/admin/DeviceDrawer.tsx:155`
**Issue:** The code reads a `last_pairing_code` field via an unsafe cast:
```typescript
const pendingCode = (device as DeviceRow & { last_pairing_code?: string }).last_pairing_code
```
`DeviceRow` (in `frontend/src/api/devices.ts:33-40`) does not include `last_pairing_code` as a field. The cast disguises the access; at runtime, `pendingCode` will always be `undefined` because the API never returns this field in the current `DeviceRow` shape. This means the "BIND TO PROFILE" → pick-profile flow for PENDING devices will always fall back to the code-entry mode (line 162), never taking the fast-path `bindDevice({ code: pendingCode, profile_id: profileId })` branch. If the intent is that `last_pairing_code` should come from the API, the field needs to be added to the backend response and to the `DeviceRow` interface. If this fast-path is not yet implemented in the backend, the cast is at minimum misleading and should be replaced with a comment explaining the unimplemented state.

**Fix:** Either add `last_pairing_code?: string` to `DeviceRow` (and update the backend) or remove the dead fast-path branch and always fall through to code-entry for PENDING bind-to-profile:
```typescript
// Current backend does not return last_pairing_code — always fall back to code entry
setDrawerMode('bind-code')
setSaveError(null)
```

---

### WR-05: `fetchNewCode` in `PairView` captures stale `isCodeFetching` via `useCallback` with empty deps

**File:** `frontend/src/routes/kiosk/PairView.tsx:84-106`
**Issue:** `fetchNewCode` is defined with `useCallback(async () => { if (isCodeFetching) return ... }, [])` — the dependency array is empty (the eslint-disable comment on line 105 suppresses the warning). `isCodeFetching` is a state variable, so the callback captures its value from the first render (`false`) forever. The guard `if (isCodeFetching) return` at line 85 will never prevent a concurrent fetch triggered by the auto-reroll path (line 166), because `isCodeFetching` always reads `false` inside the callback regardless of the actual state. In practice on slow networks, two simultaneous `POST /api/devices/pairing-codes` requests can race; the second `setPairingCode(data)` call wins and the countdown resets to a fresh code, while the first fetch's `setIsCodeFetching(false)` in the `finally` block may briefly show an inconsistent loading state.

**Fix:** Use a `useRef<boolean>` instead of relying on the state guard inside the callback:
```typescript
const isFetchingRef = useRef(false)
const fetchNewCode = useCallback(async () => {
  if (isFetchingRef.current) return
  isFetchingRef.current = true
  // ... rest of fetch
  try { ... } finally { isFetchingRef.current = false }
}, []) // empty deps is safe now — ref is always current
```

---

## Info

### IN-01: `font-size: 13px` hardcoded in `pair.css` — magic number, no token

**File:** `frontend/src/routes/kiosk/pair.css:226`
**Issue:** `.pair-qr-caption { font-size: 13px; }` uses a raw pixel value not covered by the token system. The CLAUDE.md convention is to use `--gruvax-*` tokens for all size values. This is the only raw font-size in `pair.css`.

**Fix:** Use the closest token: `font-size: var(--gruvax-text-body-sm);` (typically 13–14px per the token set).

---

### IN-02: `border-radius: 100px` magic number in `admin.css`

**File:** `frontend/src/routes/admin/admin.css:4604`
**Issue:** `.import-suggestion-chip { border-radius: 100px; }` uses a raw integer rather than `var(--gruvax-radius-pill)`, which is the project token for pill-shaped elements.

**Fix:**
```css
border-radius: var(--gruvax-radius-pill);
```

---

### IN-03: `role:` CSS pseudo-property at line 4652 is dead but visually confusing

**File:** `frontend/src/routes/admin/admin.css:4652`
**Issue:** (Also covered by WR-02.) Beyond the accessibility impact, the presence of `role: alert;` as CSS text makes the stylesheet misleading for future maintainers who may assume accessibility semantics can be declared in CSS. It should be deleted regardless of whether the HTML-side `role="alert"` fix is applied.

---

### IN-04: QR `bgColor`/`fgColor` accept CSS variable strings — depends on library internals

**File:** `frontend/src/routes/kiosk/PairView.tsx:314-315`
**Issue:** The `react-qr-code` library's `bgColor` and `fgColor` props are passed CSS variable strings (`"var(--gruvax-white)"` and `"var(--gruvax-blue)"`). The library sets these as SVG `fill` attributes. SVG `fill` attributes do not resolve CSS custom properties unless the SVG is inline and the `var()` reference is in a style attribute (not a presentation attribute). In practice, QR codes rendered as SVG with `fill="var(--gruvax-blue)"` will show as the browser default (likely black/white), not the token colors, in most browsers. This is a token-compliance workaround that likely does not work as intended. The hex fallbacks should be used here, or the SVG element should be styled via CSS class rather than presentation attributes.

**Fix:** Use literal hex values for the QR SVG presentation attributes (this is one of the few acceptable exceptions to the no-hardcoded-hex rule, since CSS vars cannot be used in SVG presentation attributes):
```tsx
bgColor="#F7F9FC"  {/* --gruvax-off-white */}
fgColor="#0051A2"  {/* --gruvax-blue */}
```
Or style the SVG element via CSS.

---

### IN-05: `admin.css` `#000` in mask-image — technically a hardcoded hex

**File:** `frontend/src/routes/admin/admin.css:1684-1685,1689-1690`
**Issue:** The mask-image gradient uses `#000` as the mask alpha channel:
```css
mask-image: linear-gradient(90deg, #000 calc(100% - 14px), transparent);
```
CSS `mask-image` uses the alpha channel of `#000` (fully opaque black) to indicate "show this area". There is no `--gruvax-*` equivalent for this mask semantics. This is a documented CSS masking pattern where `#000` is a technical artifact of the mask-image spec (not a design color choice), so it does not violate the spirit of the token rule. However, the CI grep that scans for `#[0-9a-fA-F]{3,6}` will match these lines. A comment explaining the exception should be added so the CI grep can be taught to allow it, or the grep pattern should have an exemption.

**Fix:** Add an inline comment to document that `#000` is the CSS mask channel sentinel, not a design color:
```css
/* mask-sentinel: #000 is the CSS mask alpha channel — not a design color token */
-webkit-mask-image: linear-gradient(90deg, #000 calc(100% - 14px), transparent);
mask-image: linear-gradient(90deg, #000 calc(100% - 14px), transparent);
```

---

_Reviewed: 2026-06-01_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

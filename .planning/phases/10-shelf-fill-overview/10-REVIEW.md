---
phase: 10-shelf-fill-overview
reviewed: 2026-06-02T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - frontend/src/api/types.ts
  - frontend/src/routes/admin/LocatorHeader.tsx
  - frontend/src/routes/admin/LocatorHeader.test.tsx
  - frontend/src/routes/admin/ShelfBinList.tsx
  - frontend/src/routes/admin/ShelfBinList.sse.test.tsx
  - frontend/src/routes/admin/admin.css
findings:
  critical: 0
  warning: 3
  info: 2
  total: 5
status: resolved
resolution: "All 3 warnings fixed in commit b24e7c6 (WR-01 button reset + focus-visible ring; WR-02 popover horizontal flip; WR-03 overview aria-label) with +4 regression tests. Info findings (IN-01 spacing-exception comments, IN-02 cubes-absent test coverage) accepted as non-blocking."
---

# Phase 10: Code Review Report

**Reviewed:** 2026-06-02
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Phase 10 correctly adds fill-shading and a tap-to-reveal popover to `LocatorHeader`, fixes the `AdminCube` type, and introduces the first admin-route SSE consumer (`useAdminCubesInvalidation`). The XSS threat (T-10-01) is properly mitigated — all server data renders as React text nodes. The SSE lifecycle (open on mount, close on unmount) is correctly implemented. The design-token convention is upheld: no hardcoded hex colours in the new CSS block.

Three issues require attention. The most actionable is a visual regression affecting all four button-rendered mini-Kallax cells: the `.locator-cell` base rule is missing the button-reset declarations that every other interactive admin element carries, which will produce browser-default button chrome (gray background border, no pointer cursor) on the new `<button>` elements. Two additional items are lower-severity: a misleading ARIA label on the grid wrapper in overview mode, and a popover overflow for right-column cells.

## Warnings

### WR-01: `.locator-cell` missing button-reset CSS — default browser border and no pointer cursor

**File:** `frontend/src/routes/admin/admin.css:1639`

**Issue:** The new code changes `.locator-cell` elements from `<div>` to `<button type="button">`, but the `.locator-cell` rule adds no button-reset properties. Every other interactive `<button>` in `admin.css` (e.g. `.sbl-back` at line 3038) explicitly sets `border: none`, `background: transparent`, `cursor: pointer`, and `touch-action: manipulation`. Without these, Chromium will render a gray 3D-border on each mini-Kallax cell and show the default `auto` cursor, breaking the Nordic Grid aesthetic. The `background` property is overridden by `.locator-cell--fill/--dim/--lit/--empty`, so colour is fine, but the browser border is not. There is also no `focus-visible` ring defined for the cell, so keyboard navigation produces no visible focus indicator (a WCAG 2.4.7 failure on an interactive element).

**Fix:**
```css
.locator-cell {
  width: var(--gruvax-cell-size-sm);
  height: var(--gruvax-cell-size-sm);
  border-radius: var(--gruvax-cell-radius-sm);
  /* Button reset (element changed from div → button in Phase 10) */
  border: none;
  background: transparent;
  padding: 0;
  cursor: pointer;
  touch-action: manipulation;  /* eliminates 300ms tap delay on mobile */
}

.locator-cell:focus-visible {
  outline: 2px solid var(--gruvax-blue);
  outline-offset: 2px;
}
```

---

### WR-02: Popover overflows the grid container for columns 1–3

**File:** `frontend/src/routes/admin/LocatorHeader.tsx:208`

**Issue:** The popover left edge is anchored at `activeCol * (cell-size + gap)`. At `--gruvax-cell-size-sm` (28px) and `--gruvax-cell-gap-sm` (4px), the 4-column grid wrapper is 124px wide. The popover's `min-width: 120px` (admin.css:1688) means that for columns 1, 2, and 3 the popover will extend 28px, 60px, and 92px respectively beyond the right edge of the wrapper. Since `.locator-mini-grid-wrap` has no `overflow: hidden`, the popover escapes its containing block and can be clipped by a parent or overlap unrelated content. Column 0 fits (0 + 120 = 120px, inside 124px).

**Fix — option A (smart anchor):** Clamp the left offset so the popover never exceeds the wrapper width:
```tsx
left: `min(
  calc(${activeCol} * (var(--gruvax-cell-size-sm) + var(--gruvax-cell-gap-sm))),
  calc(4 * (var(--gruvax-cell-size-sm) + var(--gruvax-cell-gap-sm)) - 120px)
)`,
```
**Fix — option B (widen wrapper):** Drop `min-width` from the popover and use `width: max-content` with a max-width constrained to the header card's safe area — the popover content is at most ~"A16 · 999 records · 999%" which measures around 200px in DM Mono at the caption size. Anchor relative to the `locator-header` container rather than the mini grid.

---

### WR-03: Misleading `aria-label` on the grid wrapper when no bin is edited

**File:** `frontend/src/routes/admin/LocatorHeader.tsx:144`

**Issue:** The grid wrapper always emits:
```
aria-label="Mini Kallax — edited bin at row {row + 1}, col {col + 1}"
```
When `ShelfBinList` renders `LocatorHeader` in overview mode (`row=-1, col=-1`), this resolves to **"Mini Kallax — edited bin at row 0, col 0"**, which falsely asserts to screen-reader users that row 0 / col 0 is the edited bin. No bin is edited in overview mode; the label is factually wrong and will mislead assistive-technology users.

**Fix:**
```tsx
aria-label={
  row !== -1
    ? `Mini Kallax — edited bin at row ${row + 1}, col ${col + 1}`
    : 'Mini Kallax — shelf fill overview'
}
```

---

## Info

### IN-01: Hardcoded `2px` offset and `120px` minimum width in new CSS/TSX — not design-token values

**Files:** `frontend/src/routes/admin/admin.css:1688`, `frontend/src/routes/admin/LocatorHeader.tsx:202,206`

**Issue:** The popover positioning uses `+ 2px` offsets (TSX lines 202, 206) and `min-width: 120px` (CSS line 1688). The project convention is to use `var(--gruvax-*)` tokens for all spatial values. `2px` does not correspond to any spacing token (the smallest is `--gruvax-space-1: 4px`). `120px` is not a token. These values will drift from the design system if token values change. The `1.5px` border widths in the new CSS block (lines 1669, 1676, 1684) are consistent with the pre-existing project-wide pattern of bare `1.5px` border values and are therefore acceptable.

**Fix:** Extract the spacing to a comment-documented exception (matching the `/* spacing-exception */` pattern used elsewhere in `admin.css`), or introduce `--gruvax-border-thin: 1.5px` and `--gruvax-popover-min-width: 120px` tokens:
```css
/* spacing-exception: 2px gap between cell edge and popover — sub-space-1 density for compact grid */
```
```tsx
`calc(${activeRow + 1} * (var(--gruvax-cell-size-sm) + var(--gruvax-cell-gap-sm)) + 2px)` /* 2px: tight visual gap, below --gruvax-space-1 */
```

---

### IN-02: No test coverage for the backward-compatible `cubes`-absent path (dim/lit only)

**File:** `frontend/src/routes/admin/LocatorHeader.test.tsx`

**Issue:** All 8 tests pass `cubes={[makeCube(...)]}`. The backward-compatible branch (`cubes === undefined` → `.locator-cell--dim`) is never exercised by the new test suite. The `BinWidthEditor` and `Wizard` callers do not pass `cubes`, so this branch is live in production. A regression in the `cubes === undefined` path would be invisible to the test suite.

**Fix:** Add one test for the fallback path:
```tsx
it('falls back to locator-cell--dim when cubes prop is absent', () => {
  const { container } = render(
    <LocatorHeader unitId={1} row={-1} col={-1} />,
  )
  const cell = container.querySelector('[data-row="0"][data-col="0"]')
  expect(cell).toHaveClass('locator-cell--dim')
  expect(cell).not.toHaveClass('locator-cell--fill')
})
```

---

_Reviewed: 2026-06-02_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

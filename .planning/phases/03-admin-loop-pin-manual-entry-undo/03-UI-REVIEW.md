# UI Review — Phase 03: admin-loop-pin-manual-entry-undo

**Audit type:** Retroactive 6-pillar visual audit
**Baseline:** `03-UI-SPEC.md` design contract + Nordic Grid design language (`design/gruvax-design-language.md`)
**Overall Score:** 19/24
**Screenshots:** Not captured — no dev server detected at localhost:3000 or localhost:5173 (code-only audit)

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 2/4 | Wrong-PIN message truncated; phantom warning diverges from spec; "SUGGEST MIDPOINT" uses wrong button style |
| 2. Visuals | 3/4 | AlphaRail has no active-letter indicator; FillBar color logic inverted in admin component |
| 3. Color | 3/4 | No hardcoded hex values; admin FillBar default fill is yellow (should be blue-light); `diff-validate-error` class undeclared |
| 4. Typography | 3/4 | Two off-spec font sizes (10px) in badge elements; `cube-card-label--last` uses 14px Space Grotesk weight 700 (mixing font families) |
| 5. Spacing | 3/4 | Raw px values in badge paddings (2px 6px, 2px 8px); diff-mini-grid uses `gap: 4px` hardcoded not `var(--gruvax-space-1)` |
| 6. Experience Design | 4/4 | Full state coverage: loading/error/empty/disabled/confirmation all present; ARIA roles correct throughout |

**Overall: 19/24**

---

## Top 3 Priority Fixes

1. **Admin FillBar color logic inverted** — Users see yellow bars for low-fill cubes (<80%) instead of the spec-mandated blue-light, and error-color only kicks in at >80% instead of >100%. The spec table is unambiguous: 1–79% = `--gruvax-blue-light`, 80–100% = `--gruvax-yellow`, >100% = `--gruvax-error`. The admin `FillBar.tsx` JSDoc *also documents the wrong thresholds* (`yellow at ≤80%, error at >80%`) — it matches the buggy code rather than the spec. The kiosk `FillBar.tsx` JSDoc and code implement all three tiers correctly. Fix: change `const isOverFull = fillLevel > 0.8` → three-tier logic matching the kiosk `FillBar.tsx` (blue-light / yellow / error), and correct the admin JSDoc to match.

2. **Wrong-PIN copy truncated; phantom warning copy diverges from spec** — `PinOverlay.tsx` line 167 renders `'Incorrect PIN'` (no trailing period or "Try again."). The UI-SPEC copywriting contract specifies `"Incorrect PIN. Try again."` — the period and action instruction are missing. Separately, `CubeEditor.tsx` lines 439/519 show `"Not in collection — verify label/catalog."` but the spec mandates `"No match in collection. Did you mean one of these?"`. These are branded, user-facing error messages that should match the contract exactly.

3. **`diff-validate-error` CSS class is declared in TSX but never defined in admin.css** — `DiffPreviewSheet.tsx` line 312 applies `className="diff-validate-error"` to the validation-error banner before commit, but this class does not appear anywhere in `admin.css`. The element renders with zero styling — no background, no color token, no visual differentiation from the surrounding content. Users will see the error message text with no warning treatment, creating a silent failure that blocks commit without explaining why.

---

## Detailed Findings

### Pillar 1: Copywriting (2/4)

**WARNING — Wrong-PIN message truncated**
- File: `frontend/src/routes/admin/PinOverlay.tsx`, line 167
- Implemented: `'Incorrect PIN'`
- Spec §A: `"Incorrect PIN. Try again."`
- Missing the sentence-ending period and the "Try again." instruction that helps users understand the action. This is a branded UI string mismatch.

**WARNING — Phantom warning copy does not match spec**
- Files: `frontend/src/routes/admin/CubeEditor.tsx`, lines 439, 519
- Implemented: `"Not in collection — verify label/catalog."`
- Spec §Copywriting Error States: `"No match in collection. Did you mean one of these?"`
- The implemented copy is passive and doesn't lead the user toward the near-miss chips. The spec copy explicitly invites action.

**WARNING — "SUGGEST MIDPOINT" button uses secondary outline style, spec calls for text+underline**
- File: `frontend/src/routes/admin/CubeEditor.tsx`, line 561; `admin.css` lines 933–956
- Implemented: `editor-btn-secondary` class (outlined border, solid background on hover)
- Spec §D: `"Suggest Midpoint button" — Barlow Condensed 700 14px --gruvax-blue, underline on hover`
- The spec explicitly calls for an inline text action (link-style), not a bordered secondary button. The outlined button overweights this action visually and changes the hierarchy.

**PASS — Spec CTAs present and correct:**
- `COMMIT CHANGE SET` (DiffPreviewSheet.tsx:329) — matches
- `BACK TO EDITOR` (DiffPreviewSheet.tsx:337) — matches
- `REVERT` / `KEEP CHANGES` confirm dialog (HistoryView.tsx:219, 226) — matches spec copywriting contract
- `SAVE NEW PIN` (Settings.tsx:138) — matches (with loading variant "SAVING…")
- Empty state "No changes yet" + body copy (HistoryView.tsx:127–129) — exact match to spec
- Rate-limit countdown (`Too many attempts. Try again in {N}s.`) — matches spec

### Pillar 2: Visuals (3/4)

**WARNING — AlphaRail has no active-letter visual indicator**
- File: `frontend/src/routes/admin/AlphaRail.tsx`, `admin.css` lines 449–492
- Spec §D: `"active letter: --gruvax-blue background + --gruvax-white text"`
- The CSS defines `.alpha-rail-btn--inactive` (opacity 0.25 for non-matching letters) but there is no `.alpha-rail-btn--active` or equivalent class. The component never applies an active state to the currently-jumped-to letter. Users cannot tell which letter position the list is scrolled to. The `alpha-rail-btn` hover state uses `color-mix(in srgb, var(--gruvax-blue) 10%, transparent)` background (not the spec's solid blue + white text).

**WARNING — Admin FillBar (admin/FillBar.tsx) inverted color logic**
- File: `frontend/src/routes/admin/FillBar.tsx`, line 27
- `const isOverFull = fillLevel > 0.8` → applies `.fill-bar-fill--warn` (which maps to `--gruvax-error`)
- `.fill-bar-fill` (default) uses `--gruvax-yellow`
- The result: a cube at 50% fill shows a yellow bar (spec: `--gruvax-blue-light`); a cube at 90% shows an error-red bar (spec: `--gruvax-yellow`); overstuffed (>100%) is unreachable from the current logic
- The kiosk `FillBar.tsx` correctly implements all three tiers; the admin version has different, incorrect logic
- Visual impact: fill bars communicate wrong urgency across the entire admin cubes grid

**PASS — Drag handle on kiosk panel present** (kiosk.css:634; `.cube-panel__handle`)
**PASS — Scrim dismiss implemented** (`CubeContentsPanel.tsx` line 76 `cube-panel-scrim` with `onClick={onDismiss}`)
**PASS — Slide-up animation present** (kiosk.css:625, `animation: panel-slide-up 300ms var(--gruvax-ease-decelerate)`)
**PASS — Mini Kallax diff grid with changed-cube ring** (DiffPreviewSheet.tsx:197, `.diff-mini-cell--changed` with `border-color: var(--gruvax-blue)`)
**PASS — PIN dots with filled/error state** (admin.css:96–104)

### Pillar 3: Color (3/4)

**BLOCKER-LEVEL DEFECT — `diff-validate-error` CSS class undefined**
- File: `frontend/src/routes/admin/DiffPreviewSheet.tsx`, line 312 (`className="diff-validate-error"`)
- `admin.css` grep: zero matches for `.diff-validate-error`
- The validation-error banner that appears above the COMMIT button (when cubes have order/phantom errors) renders as an unstyled `<div>`. No background, no color token, no visual distinction from surrounding content. The error text appears but in default black, indistinguishable from normal body text.
- Fix: add `.diff-validate-error { ... color: var(--gruvax-error); background: color-mix(...); }` to `admin.css` following the pattern of `.diff-warning--empty`

**WARNING — Admin FillBar default fill uses --gruvax-yellow instead of --gruvax-blue-light**
- File: `admin.css`, lines 437–441
- `.fill-bar-fill { background: var(--gruvax-yellow); }` — this is the default (0–80%) state
- Spec (UI-SPEC §C, §I): `0–79%: --gruvax-blue-light fill`; `80–100%: --gruvax-yellow fill`
- The yellow fill is spec-reserved for near-full state; using it as default undermines the visual signal

**PASS — Zero hardcoded hex values in any admin or kiosk component** — grep `#[0-9a-fA-F]{3,8}` in `.tsx` files returns no matches. All color references use `var(--gruvax-*)` tokens or `color-mix()` expressions over tokens.

**PASS — Accent (--gruvax-blue) appears 49 times across CSS** — used on headings, primary buttons, borders, focus rings, and the diff-changed-cube ring. Not overused as a generic interactive color for every clickable element. Near-miss chips and phantom chips use `--gruvax-blue-light` (secondary), not the primary accent.

**PASS — --gruvax-error correctly reserved for destructive/revert confirmation button and fill bar overstuffed state only**

### Pillar 4: Typography (3/4)

**WARNING — Two 10px font sizes used for badge elements (off-spec)**
- Files: `admin.css`, lines 592, 1385
- `.cube-card-empty-badge { font-size: 10px; }` (cube grid empty badge)
- `.history-source-badge { font-size: 10px; }` (history card EDIT/UNDO badge)
- Spec Typography: declared sizes are 36px, 16px, 14px, 11px — no 10px size
- 10px is below the spec's "micro-label" tier of 11px. These badges fall below the smallest declared size.
- Fix: use `--gruvax-text-mono-sm` (11px) or `--gruvax-text-label` (11px).

**WARNING — `cube-card-label--last` mixes font family and weight incorrectly**
- File: `admin.css`, lines 622–626
- `.cube-card-label--last { color: var(--gruvax-text-secondary); font-size: var(--gruvax-text-body-sm, 14px); font-weight: 700; }`
- This class overrides `.cube-card-label` (which is Barlow Condensed 700 16px) with `14px font-weight: 700` but does NOT change `font-family`, so it inherits Barlow Condensed 700 at 14px — however the spec's 14px role is Space Grotesk 400. The combined result is a display font at 14px weight 700, which is neither the spec's 14px body role nor the spec's display role.

**PASS — Declared spec sizes all present in implementation:** `--gruvax-text-display-lg` (36px) on headings, keypad digits, settings heading; `--gruvax-text-display-sm` (16px) on form labels, card sub-headings, button labels; `--gruvax-text-body-sm` (14px) on helper text, error messages; `--gruvax-text-mono-sm` (11px) on timestamps and fill % labels.

**PASS — Font family discipline maintained:** Barlow Condensed for ALL CAPS labels and display text; Space Grotesk for body/instructions; DM Mono for catalog numbers, countdown, PIN display. No cross-family violations beyond the `cube-card-label--last` noted above.

**INFORMATIONAL — `--gruvax-text-display-md` (24px) appears 2× in typography grep** — not in the Phase 3 spec's 4-size budget. Appears to be inherited from the Phase 1/2 kiosk CSS rather than newly introduced in Phase 3 admin components.

### Pillar 5: Spacing (3/4)

**WARNING — Badge paddings use raw pixel values**
- File: `admin.css`, lines 599 (`padding: 2px 6px`), 1392 (`padding: 2px 6px`), 1413 (`padding: 2px 8px`)
- Affected: `.cube-card-empty-badge`, `.history-source-badge`, `.history-reverted-pill`
- Spec constraint: "Use token names in CSS; never write raw pixel values."
- `2px` is below `--gruvax-space-1` (4px) minimum — no token covers 2px. This is a deliberate spec exception not documented in the Phase 3 spacing scale.
- Fix: if 2px is intentionally needed for pill padding, document it as a named exception, or accept `--gruvax-space-1` (4px) for vertical padding.

**WARNING — DiffPreviewSheet mini-grid uses hardcoded `gap: 4px`**
- File: `admin.css`, line 1063 (`.diff-mini-grid { gap: 4px; }`)
- Should be `gap: var(--gruvax-space-1)` (which equals 4px) to stay on the token system
- Minor but breaks the "never write raw pixel values" constraint

**WARNING — `.cubes-unit-grid` uses `minmax(140px, 1fr)` arbitrary value**
- File: `admin.css`, line 543
- `grid-template-columns: repeat(auto-fill, minmax(140px, 1fr))`
- 140px is not in the spacing scale or cell-size tokens. No token covers this breakpoint. Acceptable as a grid layout detail but worth documenting.

**PASS — All major structural spacing uses `var(--gruvax-space-*)` tokens**: card padding (`--gruvax-space-4`, `--gruvax-space-5`), section gaps (`--gruvax-space-3` through `--gruvax-space-7`), button padding (`--gruvax-space-2`/`--gruvax-space-4`), PIN dot gap (`--gruvax-space-2`).

**PASS — Keypad tap targets**: `.keypad-key { min-width: 80px; min-height: 56px }` (mobile) and `@media (min-width: 768px) { min-height: 64px }` — meets the spec's 80×56px mobile / 80×64px kiosk requirement.

**PASS — Alpha rail button**: `width: 32px; min-height: 44px` — matches spec exactly.

**PASS — outline-offset: 2px** on focus rings — consistent throughout, not a spacing-scale violation (this is an outline property, not margin/padding).

### Pillar 6: Experience Design (4/4)

All major state coverage requirements are met. No gaps found.

**Loading states:**
- `CubesGrid.tsx`: `isLoading` → `.cubes-grid-loading` with `aria-live="polite"`
- `CubeEditor.tsx`: `boundaryLoading` → `.cube-editor-loading` with `aria-live="polite"`
- `HistoryView.tsx`: `isLoading` → `.history-loading` with `aria-live="polite"`
- `DiffPreviewSheet.tsx`: `isValidating` → `.diff-sheet-validating`

**Error states:**
- `CubesGrid.tsx`: `isError` → `"Failed to load cubes. Please try again."`
- `HistoryView.tsx`: `isError` → `.history-error` with `role="alert"`
- `DiffPreviewSheet.tsx`: network error → `"Could not save — check your connection and try again."`
- `CubeEditor.tsx`: midpoint failure → user-visible error message
- `Settings.tsx`: save failure → `role="alert"` error paragraph

**Empty states:**
- History view empty: `"No changes yet"` + body (exact spec match)
- Cube contents panel empty (is_empty): `"No records assigned to this cube yet."` — matches spec
- Cube contents panel (set but empty): `"Nothing in this cube"` + explanation — matches spec
- Diff preview sheet empty: `"No pending changes to preview."` — added beyond spec requirement

**Disabled states:** COMMIT button disabled during `isCommitting || isValidating || hasValidationErrors`; keypad disabled during PIN submission; catalog# field disabled until label selected.

**Destructive confirmation:** Revert confirm dialog implemented with correct copy (`role="dialog"`, REVERT + KEEP CHANGES buttons). The USE ANYWAY phantom force path also requires explicit button tap.

**ARIA coverage:** `role="dialog"` + `aria-modal="true"` on PIN overlay; `role="timer"` on countdown; `role="alert"` on error messages; `aria-live="polite"` on loading states; `aria-label` on all icon-only buttons (Lock screen, Log out); keypad keys have `type="button"` and `aria-label` on backspace.

---

## Registry Safety

Not applicable. `components.json` (shadcn) not present. No third-party registries declared in UI-SPEC.md.

---

## Files Audited

**Frontend components:**
- `frontend/src/routes/admin/PinOverlay.tsx`
- `frontend/src/routes/admin/AdminShell.tsx`
- `frontend/src/routes/admin/CubeEditor.tsx`
- `frontend/src/routes/admin/CubesGrid.tsx` (via grep)
- `frontend/src/routes/admin/DiffPreviewSheet.tsx`
- `frontend/src/routes/admin/HistoryView.tsx`
- `frontend/src/routes/admin/FillBar.tsx` (admin)
- `frontend/src/routes/admin/AlphaRail.tsx`
- `frontend/src/routes/admin/admin.css`
- `frontend/src/routes/kiosk/FillBar.tsx`
- `frontend/src/routes/kiosk/CubeContentsPanel.tsx`
- `frontend/src/routes/kiosk/kiosk.css` (selected sections)

**Design system:**
- `design/gruvax-design-tokens.css`
- `design/gruvax-design-language.md`

**Planning artifacts:**
- `.planning/phases/03-admin-loop-pin-manual-entry-undo/03-UI-SPEC.md`
- `.planning/phases/03-admin-loop-pin-manual-entry-undo/03-CONTEXT.md`
- Phase 03 SUMMARY files (01 through 05)

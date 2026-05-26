---
phase: 7
slug: wizards-import-export
status: approved
shadcn_initialized: false
preset: none
created: 2026-05-24
reviewed_at: 2026-05-24
---

# Phase 7 — UI Design Contract: Wizards + Import/Export

> Visual and interaction contract for the four new admin surfaces introduced in Phase 7:
> the `/admin/wizard` route (setup + reshuffle), the `/admin/import` route, the
> "Continue your reshuffle" banner, and the post-commit confirmation surface.
> Consumed by gsd-planner, gsd-executor, and gsd-ui-auditor.

All design decisions are grounded in:
- Nordic Grid design language (`design/gruvax-design-language.md`)
- Token contract (`design/gruvax-design-tokens.css` / `.json`)
- Sketch findings (`.claude/skills/sketch-findings-gruvax/references/boundary-editing.md`)
- Locked CONTEXT.md decisions D-01…D-15
- Verified RESEARCH.md endpoint + component inventory

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none — vanilla DOM via `el()` helper + `replaceChildren()`. Never `innerHTML`. |
| Preset | not applicable |
| Component library | none — project builds from raw HTML elements + design tokens |
| Icon library | Inline SVG (Lucide icons, inlined as in existing admin components — no external icon package) |
| Font | Barlow Condensed 700/900 (display/labels), Space Grotesk 400/500 (UI body), DM Mono 400/500 (catalog numbers, IDs, counts) — loaded via `@import` in `design/gruvax-design-tokens.css` |

No shadcn gate needed — project explicitly uses vanilla DOM with `el()`/`replaceChildren()`, pre-dating and precluding shadcn.

---

## Spacing Scale

Source: `design/gruvax-design-tokens.css` `--gruvax-space-*` (all existing, consume tokens).

| Token | CSS Variable | Value | Usage in Phase 7 |
|-------|-------------|-------|------------------|
| xs | `--gruvax-space-1` | 4px | Icon-to-label gaps, inline badge padding |
| sm | `--gruvax-space-2` | 8px | Between wizard nav buttons, between step counter and heading |
| md | `--gruvax-space-4` | 16px | Wizard step body padding, import row padding, banner padding |
| lg | `--gruvax-space-5` | 24px | Section breaks inside import diff, wizard LocatorHeader margin-bottom |
| xl | `--gruvax-space-6` | 32px | Page-level padding (wizard and import routes), banner vertical padding |
| 2xl | `--gruvax-space-7` | 48px | Vertical space between wizard step and commit row |
| 3xl | `--gruvax-space-8` | 64px | Not used in Phase 7 |

Exceptions:
- Touch targets (tap buttons: CONTINUE, SKIP, COMMIT, DISCARD): minimum 44px height enforced via `min-height: 44px` on all interactive elements per mobile-first constraint. This is not a spacing token — it is a touch-target floor.
- The "Discard" confirmation dialog stacks two 48px-min-height buttons with `--gruvax-space-2` (8px) between them.

---

## Typography

Source: `design/gruvax-design-tokens.css` typography section. No new sizes introduced.
Rules: Barlow Condensed is ALL CAPS for every label. Space Grotesk is sentence case for instructions and body copy. DM Mono for all data values (catalog#, change_set_id, counts, step indicators).

### Fonts by role

| Role | Font | CSS Variable | Size | Weight | Letter-spacing | Line Height | Usage in Phase 7 |
|------|------|-------------|------|--------|---------------|-------------|-----------------|
| Section heading / ALL-CAPS label | Barlow Condensed | `--gruvax-font-display` | `--gruvax-text-display-sm` (16px) | 700 | `--gruvax-tracking-label` (0.14em) | `--gruvax-leading-tight` (1.1) | Nav tab labels (WIZARD, IMPORT, HISTORY), step label ("STEP 7 OF 32"), banner action labels (CONTINUE, DISCARD), confirmation heading |
| Body instruction | Space Grotesk | `--gruvax-font-ui` | `--gruvax-text-body` (16px) | 400 | 0 | `--gruvax-leading-normal` (1.5) | Wizard step question ("What's the first record in this bin?"), import instructions, banner explanation text, error descriptions |
| Small instruction / caption | Space Grotesk | `--gruvax-font-ui` | `--gruvax-text-body-sm` (14px) | 400 | 0 | `--gruvax-leading-normal` (1.5) | Import error row descriptions, "approximate" label on movement counts, "did you mean" suggestion body |
| UI label / micro | Space Grotesk | `--gruvax-font-ui` | `--gruvax-text-caption` (12px) | 500 | 0 | `--gruvax-leading-normal` (1.5) | Straddle symbol (`↪`), cube address overlay in diff grid, is_empty badge |
| Data readout | DM Mono | `--gruvax-font-mono` | `--gruvax-text-mono` (14px) | 400 | 0 | `--gruvax-leading-normal` (1.5) | Catalog numbers in RecordPickerSheet, `change_set_id` in confirmation, movement counts (e.g. "+12 records"), row numbers in import error list, step numbers ("14/32") |
| change_set_id display | DM Mono | `--gruvax-font-mono` | `--gruvax-text-mono-lg` (16px) | 500 | 0 | `--gruvax-leading-tight` (1.1) | Confirmation surface — the UUID is prominent |

Summary: 4 sizes in active use (16, 14, 12, 11px). **Weights are capped at exactly 2 per typeface** — Barlow Condensed 700 (labels) + 900 (page-level display headings only, e.g. `IMPORT BOUNDARIES`, `BOUNDARIES COMMITTED`), Space Grotesk 400 + 500, DM Mono 400 + 500. The four distinct weight values (400/500/700/900) are required by the locked Nordic Grid design language (`design/gruvax-design-language.md`, CLAUDE.md): Barlow Condensed is a display font and uses 900 only for top-level headings, never in body or interactive copy. No single weight crosses typeface families.

---

## Color

Source: `design/gruvax-design-tokens.css`. No hardcoded hex anywhere. Full 60/30/10 distribution:

| Role | CSS Variable | Hex value | % | Usage in Phase 7 |
|------|-------------|-----------|---|-----------------|
| Dominant surface | `--gruvax-white` | #FFFFFF | ~60% | Wizard route background, import route background, confirmation surface background, banner background |
| Secondary surface | `--gruvax-off-white` | #F7F9FC | ~30% | Import error rows (bg tint on error cards), wizard step card bg, settings export section bg |
| Accent — CHANGED / ACTIVE | `--gruvax-yellow` | #FFDA00 | ~10% | **Reserved-for list below** |
| Accent — STRUCTURE / interactive | `--gruvax-blue` | #0051A2 | structural | Top bar, nav tabs, LocatorHeader lit cell fill (wizard current step), commit button bg, CONTINUE button bg, focus ring |
| Destructive | `--gruvax-error` | #C0392B | minimal | DISCARD button text + border in confirmation dialog only |

### Accent (`--gruvax-yellow` / `--gruvax-yellow-dark`) reserved for exactly these elements:

1. The LocatorHeader mini-Kallax cell at the **current wizard step** — lit yellow with `--gruvax-shadow-led`
2. **Import diff-preview** — cubes whose cut point is **changing** render lit yellow (same as existing changed-state convention from Phase 3/5)
3. The **"Continue your reshuffle" banner** background tint: `--gruvax-yellow-faint` (`rgba(255,218,0,0.12)`) with a left-border in `--gruvax-yellow-dark`
4. The **progress indicator fill** (step progress bar) in the wizard
5. The `NEW` bin badge (if a future phase adds new-bin creation in wizard — not Phase 7 scope; not used here)
6. Focus rings on interactive wizard step controls (RecordPickerSheet trigger, SKIP button)

Yellow is NEVER used for passive structure, body text, or inactive states.

### Semantic colors

| Token | Hex | Usage |
|-------|-----|-------|
| `--gruvax-success` | #1A7A4A | Confirmation checkmark icon, "committed" state in confirmation surface |
| `--gruvax-warning` | #E6A800 | Stale-draft re-validate warning chips (cut records no longer in collection) |
| `--gruvax-error` | #C0392B | Import per-row error state (row border + label), DISCARD button |
| `--gruvax-overlay-scrim` | rgba(0,40,85,0.55) | RecordPickerSheet backdrop (existing pattern, unchanged) |

---

## Surface Contracts

### Surface 1: `/admin/wizard` — Wizard Route (D-01, D-02, D-03, D-04, ADMN-04, ADMN-10)

**Layout — full page, mobile-first (390px baseline)**

```
┌────────────────────────────────────┐
│ [AdminShell top bar]               │
│  SETTINGS  CUBES  HISTORY  WIZARD IMPORT │
├────────────────────────────────────┤
│  LocatorHeader (mini-Kallax)       │  ← current step lit yellow, 28px cells
│  SHELF A · STEP 7 / 32            │  ← Barlow Condensed 700, ALL CAPS
│  ══════════════════════░░░░░░░░░   │  ← progress bar (yellow fill, blue track)
├────────────────────────────────────┤
│  What's the first record           │  ← Space Grotesk 400 16px, sentence case
│  in this bin?                      │
│                                    │
│  [RecordPickerSheet trigger]       │  ← reused Phase 5 component
│   PICK A RECORD                    │  ← 44px min-height button
│                                    │
│  ── or ──                          │
│  [THIS BIN IS EMPTY / SKIP]       │  ← 44px min-height, blue outline style
├────────────────────────────────────┤
│  [← BACK]  [NEXT →]               │  ← 44px min-height, full-width on mobile
│  (BACK disabled on step 1)         │
└────────────────────────────────────┘
```

**LocatorHeader in wizard context**

The existing `LocatorHeader` component is reused with a new `totalSteps` prop to show step context:
- Mini 4×4 Kallax grid: 28px cells (`--gruvax-cell-size-sm`), 4px gap (`--gruvax-cell-gap-sm`)
- Current step cell: lit yellow (`--gruvax-cell-lit`) with LED glow (`--gruvax-shadow-led`)
- Cells already confirmed in this walk: `--gruvax-cell-selected` (dark blue) — indicates "done"
- Cells not yet reached: `--gruvax-cell-dim`
- Label row: `SHELF A · STEP 7 / 32` — Barlow Condensed 700, `--gruvax-text-display-sm` (16px), ALL CAPS, `--gruvax-tracking-label`
- Multi-shelf: show SHELF A grid + SHELF B grid side by side at thumbnail scale (use 28px cells with 8px gap between shelf grids)

**Progress indicator**

A horizontal progress bar immediately below the LocatorHeader:
- Track: `--gruvax-blue-light` (D8E8F5), height 6px, `--gruvax-radius-pill`
- Fill: `--gruvax-yellow` (FFDA00), same height, `--gruvax-radius-pill`
- Width: `(currentStep / totalSteps) * 100%`, CSS transition 150ms linear
- No numeric label on the bar itself — step number is in the LocatorHeader label row

**RecordPickerSheet trigger button**

Reuses existing `RecordPickerSheet` from Phase 5 without modification.
- Trigger: a 44px-min-height tappable row inside a bordered card (`--gruvax-border-light` border, `--gruvax-radius-md` radius)
- When a record is set for this step: show label + catalog in the card (DM Mono 14px for catalog, Space Grotesk 14px for label name)
- Clear/change affordance: a small ✕ icon inside the card to reset the step's selection. Icon-only control — MUST carry `aria-label="Clear selected record"` (kiosk + screen-reader accessibility)

**"This bin is empty / skip" control**

- Button style: blue outline (`--gruvax-blue` border 1.5px, white bg, `--gruvax-blue` text)
- Label: `THIS BIN IS EMPTY / SKIP` — Barlow Condensed 700, ALL CAPS
- Tap sets `is_empty = true` for this step and advances to the next
- Already-skipped step: card shows `EMPTY — SKIP` chip (blue-faint background, `--gruvax-text-muted` text)

**Back/Next navigation**

- Two buttons side by side: `← BACK` (left) and `NEXT →` (right)
- On the last step: NEXT becomes `REVIEW & COMMIT`
- BACK: blue outline style, disabled + aria-disabled on step 1, opacity 0.4 when disabled
- NEXT: blue filled button (`--gruvax-blue` bg, white text), disabled until the current step has either a record picked or is_empty set
- Both: full-width on mobile (each takes 50% of the row), 44px min-height
- On the review screen (after all steps): a full-width `COMMIT ALL CHANGES` button replaces NEXT, blue filled, 48px min-height

**Two-mode visual differentiation (D-01)**

- *Fresh setup*: LocatorHeader shows all cells dim at the start of the walk
- *Reshuffle*: LocatorHeader shows all cells in `--gruvax-cell-selected` (dark blue) on load — indicating pre-loaded existing cut points — then cells transition to dim/done state as the owner re-walks
- Mode badge: a pill just below the top bar (not the progress bar) reading either `SETUP` or `RESHUFFLE` in Barlow Condensed 700, background `--gruvax-blue-faint`, text `--gruvax-blue`
- In reshuffle mode, each step's record card is pre-populated with the current cut point (shown in a lighter state — `--gruvax-text-muted` text color) and remains editable

**End-of-shelf guidance (last step)**

After the final cube, the wizard shows a blue informational card above the REVIEW & COMMIT button:
- Copy: "This is the last bin. Everything in your collection from this point forward will be shelved here."
- Font: Space Grotesk 400 14px, `--gruvax-text-secondary` color
- Icon: a right-pointing thin chevron SVG in `--gruvax-blue`

---

### Surface 2: `/admin/import` — Import Route (D-08, D-11, ADMN-05, BAK-01)

**Layout — full page, mobile-first**

```
┌────────────────────────────────────┐
│ [AdminShell top bar]               │
│  SETTINGS  CUBES  HISTORY  WIZARD IMPORT │
├────────────────────────────────────┤
│  IMPORT BOUNDARIES                 │  ← Barlow Condensed 900, display-md (24px)
│  Upload a CSV or YAML file.        │  ← Space Grotesk 400 16px
│  All cubes not in the file will    │
│  be set to empty.                  │
├────────────────────────────────────┤
│  [  DROP A FILE OR TAP TO UPLOAD ] │  ← file drop zone, 120px tall
│  Accepts: .csv, .yaml              │  ← Space Grotesk 400 12px, --gruvax-text-muted
├────────────────────────────────────┤
│  ← validation results appear here →│
└────────────────────────────────────┘
```

**File upload affordance**

- Drop zone: `--gruvax-border-light` dashed border (2px), `--gruvax-radius-lg` radius, `--gruvax-off-white` background, 120px min-height
- Label text inside zone: Barlow Condensed 700 16px ALL CAPS `DROP A FILE OR TAP TO UPLOAD`, plus a cloud/upload SVG icon (Lucide `Upload`, 24px, `--gruvax-blue`)
- On drag-over: border changes to `--gruvax-blue` solid, background to `--gruvax-blue-faint`
- On file selected: zone collapses to a compact "file chip" showing filename + size + a ✕ to clear; the zone itself hides

**Partial-import warning banner**

Appears immediately when a file is parsed and the cube count is fewer than the total cubes in the system:
- Background: `--gruvax-yellow-faint`, left border `--gruvax-yellow-dark` (4px solid)
- Icon: exclamation SVG in `--gruvax-warning`
- Copy (sentence case, Space Grotesk 400 14px): "This file defines [N] cubes. The remaining [M] cubes will be set to empty after import."
- This is not an error — it does not block commit — but it must always be visible when true

**Per-row error list**

Renders after a failed validation. Each row is a card:

```
┌──────────────────────────────────────────────────────┐
│ ROW 14  ●  UNIT 1 / BIN 6                    ERROR  │  ← header row
│ "Blue Note" · "BLP 40003" — not found             │  ← DM Mono 14px for values
│                                                      │
│ Did you mean?                                        │  ← Space Grotesk 400 14px
│  [Blue Note · BLP 4003]  [Blue Note · BLP 4000]  │  ← tappable suggestion chips
└──────────────────────────────────────────────────────┘
```

- Card border: `--gruvax-error` (1.5px), `--gruvax-radius-md` radius
- Header: Barlow Condensed 700 16px ALL CAPS; `ROW 14` in DM Mono 14px; `ERROR` badge in `--gruvax-error` bg, white text
- Catalog/label value in error: DM Mono 14px, `--gruvax-text-secondary`
- "Did you mean?" chips: pill style, `--gruvax-blue-faint` bg, `--gruvax-blue` text and border, 36px min-height, tap applies the suggestion to that row's state
- After applying a suggestion, the card transitions from ERROR border to `--gruvax-success` border, the ERROR badge becomes `FIXED`
- Contiguity violation error (different from phantom): card shows error badge `CONTIGUITY ERROR`, no suggestions chips (this requires the owner to change their walk, not just confirm a near-miss)
- Contiguity error copy (plain language): "Blue Note would be split across non-adjacent bins. Adjust this cut point to keep Blue Note in one run."

**Affected-cubes diff preview (mini-Kallax grid)**

Renders below the per-row error list (or alone when validation passes):
- Uses existing `CubesGrid` / `ShelfBinList` visual language at compact scale (`--gruvax-cell-size-md`, 40px cells, 6px gap)
- Changing cubes: lit yellow (`--gruvax-cell-lit` + `--gruvax-shadow-led`)
- Unchanged cubes: `--gruvax-cell-dim`
- Empty cubes (will become empty after import): `--gruvax-cell-empty` with dashed border
- Movement count label below each changed cube: DM Mono 11px (`--gruvax-text-mono-sm`), format: `+12` or `−8 (approx.)` — the `(approx.)` suffix is REQUIRED on all non-zero deltas per RESEARCH Pattern 2 (movement counts are approximations in v1)
- Section heading above diff: Barlow Condensed 700 16px ALL CAPS `AFFECTED CUBES`
- Count below heading: Space Grotesk 400 14px `N cubes changing · M cubes unchanged`

**Commit button state machine**

- **Disabled state** (validation errors exist or file not yet uploaded): button text `COMMIT IMPORT`, blue outline style, opacity 0.4, `cursor: not-allowed`, `aria-disabled="true"`. The button never disappears — it remains visible and disabled.
- **Enabled state** (zero validation errors): blue filled button (`--gruvax-blue` bg, white text, `--gruvax-shadow-sm` box-shadow), 48px min-height, full width
- Transition from disabled to enabled: 250ms `--gruvax-ease-standard` on opacity + background-color
- **Loading state** (after tap, awaiting server): spinner replaces label, button remains full width
- Enabled → disabled → enabled transition must not flicker on re-validation

---

### Surface 3: "Continue your reshuffle" Banner (D-06, D-07, ADMN-10, SC3)

**Placement**: Directly inside the `AdminShell` `<main>` content area, above the existing `<Outlet/>` content, rendered only when `reshuffleDraft !== null` in `adminStore`. It is always at the top of the content area — not a toast, not floating.

**Visual design**

```
┌─────────────────────────────────────────────────────────┐
│ ║  RESHUFFLE IN PROGRESS — 14 OF 32 STEPS DONE         │  ← yellow left-border
│ ║  Started 3 hours ago                                  │
│ ║  [CONTINUE]                 [DISCARD]                 │
└─────────────────────────────────────────────────────────┘
```

- Background: `--gruvax-yellow-faint` (`rgba(255,218,0,0.12)`)
- Left border: 4px solid `--gruvax-yellow-dark`
- Border-radius: `--gruvax-radius-md` (8px), no shadow (keeps it informational, not alarming)
- Outer padding: `--gruvax-space-4` (16px) horizontal, `--gruvax-space-4` (16px) vertical

**Heading row**

- `RESHUFFLE IN PROGRESS — 14 OF 32 STEPS DONE` — Barlow Condensed 700, `--gruvax-text-display-sm` (16px), ALL CAPS, `--gruvax-tracking-label`, `--gruvax-text-primary` color
- `14 OF 32` — sourced from `reshuffleDraft.completedSteps` / `totalCubes`

**Sub-line**

- `Started 3 hours ago` — Space Grotesk 400 14px, sentence case, `--gruvax-text-muted`
- Relative time from `reshuffleDraft.startedAt`

**Action buttons**

- `CONTINUE` — blue filled button (`--gruvax-blue` bg, white text, Barlow Condensed 700 16px ALL CAPS), 44px min-height, navigates to `/admin/wizard?mode=reshuffle` and triggers draft re-validate
- `DISCARD` — blue outline button with `--gruvax-error` text and border, 44px min-height, Barlow Condensed 700 16px ALL CAPS
- Buttons side by side with `--gruvax-space-2` (8px) gap between them

**Discard confirmation (inline — no modal)**

When DISCARD is tapped, the banner content replaces with an inline confirmation row:
```
Are you sure? This will delete your in-progress reshuffle draft.
[YES, DISCARD]   [KEEP DRAFT]
```
- Confirmation text: Space Grotesk 400 14px, sentence case
- `YES, DISCARD` — `--gruvax-error` filled button, 44px min-height, Barlow Condensed 700 ALL CAPS
- `KEEP DRAFT` — blue outline button, 44px min-height
- On `YES, DISCARD` tap: clears `reshuffleDraft` from localStorage + Zustand, banner disappears with 250ms fade-out

**Stale-draft re-validate display**

On CONTINUE tap, the wizard immediately calls `POST /api/admin/cubes/validate`. While validating:
- Banner shows a spinner inline (16px, `--gruvax-blue`) with copy `Checking for collection changes…`

After re-validate returns, if any step's record is stale (phantom / no longer in collection):
- A stale-record warning banner appears inside the wizard route (not the AdminShell banner):
  - Background: `--gruvax-warning` tint (`rgba(230,168,0,0.12)`), left border `--gruvax-warning`
  - Copy: "Some records in your draft are no longer in the collection. Review the highlighted steps below."
  - The affected wizard steps show the record card in a warning state (yellow border `--gruvax-warning`) with inline "did you mean" suggestion chips (matching the import error chip style)

---

### Surface 4: Post-Commit Confirmation (D-15, SC5)

**Decision: Dedicated confirmation screen, not inline toast.**

Rationale: The SC5 keystone requires naming the `change_set_id` prominently AND offering a "Revert this change set" tap that links to Phase 3 history/revert. A toast is constrained to ~300ms readability and touch-unfriendly link targets. A dedicated confirmation screen replaces the wizard/import content area and gives the `change_set_id` the visual weight it deserves as the primary audit artifact. It also makes the revert tap unambiguous on a phone screen.

**Layout**

```
┌────────────────────────────────────┐
│ [AdminShell top bar]               │
├────────────────────────────────────┤
│  ✓                                 │  ← success checkmark, 48px, --gruvax-success
│                                    │
│  BOUNDARIES COMMITTED              │  ← Barlow Condensed 900 display-md 24px
│                                    │
│  Operation: Wizard setup           │  ← Space Grotesk 400 14px, sentence case
│  Cubes updated: 32                 │
│                                    │
│  Change set                        │  ← Space Grotesk 400 12px, --gruvax-text-muted
│  a3f8c2d1-4b9e-...                 │  ← DM Mono 500 16px, --gruvax-text-primary
│  (full UUID, user can copy)        │
│                                    │
│  [REVERT THIS CHANGE SET]          │  ← 44px, blue outline
│  [BACK TO CUBES]                   │  ← 44px, blue filled
└────────────────────────────────────┘
```

**Heading by operation origin (D-04 source labels)**

| `source` value | Heading | Operation sub-line |
|---------------|---------|-------------------|
| `wizard` | `BOUNDARIES COMMITTED` | `Operation: Wizard setup · N cubes` |
| `reshuffle` | `RESHUFFLE COMMITTED` | `Operation: Reshuffle · N cubes` |
| `csv` | `IMPORT COMMITTED` | `Operation: CSV import · N cubes` |
| `yaml` | `IMPORT COMMITTED` | `Operation: YAML import · N cubes` |

All headings: Barlow Condensed 900, `--gruvax-text-display-md` (24px), ALL CAPS, `--gruvax-text-primary`

**change_set_id display**

- Label: `Change set` — Space Grotesk 400 12px, `--gruvax-text-muted`, sentence case
- Value: full UUID — DM Mono 500 16px, `--gruvax-text-primary`
- Tap-to-copy affordance: a small copy icon (Lucide `Copy`, 14px, `--gruvax-text-muted`) next to the UUID; on tap, icon briefly changes to a checkmark (`--gruvax-success`) for 1500ms. Icon-only control — MUST carry `aria-label="Copy change set ID"`

**Revert action**

- `REVERT THIS CHANGE SET` — blue outline button (`--gruvax-blue` border + text, white bg), 44px min-height, Barlow Condensed 700 16px ALL CAPS
- Tap navigates to `/admin/history` with the `change_set_id` passed as a query param (`?highlight=<id>`) which causes HistoryView to open the confirm dialog for that specific change set automatically
- This reuses the existing Phase 3 `revertChangeSet` path wholesale — no new revert logic

**Settings-import confirmation (different surface, no change_set_id)**

For settings import (BAK-02), since settings do not go through `boundary_history`, the confirmation is simpler:
- Full-screen confirmation screen (same layout as above, minus change_set_id section)
- Heading: `SETTINGS IMPORTED`
- Operation sub-line: `LED and presentation settings updated.`
- Single CTA: `BACK TO SETTINGS` — blue filled, 44px min-height

---

### Surface 5: History View — New Source Labels

The existing `HistoryView` shows a `sourceLabel` badge per change set. Extend the label map:

| `source` value | Badge label | Badge style |
|---------------|-------------|------------|
| `manual` | `EDIT` | `--gruvax-blue-faint` bg, `--gruvax-blue` text (existing) |
| `bulk` | `BULK EDIT` | `--gruvax-blue-faint` bg, `--gruvax-blue` text (existing behaviour, now labelled) |
| `revert` | `UNDO` | `--gruvax-blue-faint` bg, `--gruvax-text-muted` text (existing) |
| `cut_insert` | `CUT EDIT` | `--gruvax-blue-faint` bg, `--gruvax-blue` text (existing) |
| `wizard` | `WIZARD SETUP` | `--gruvax-yellow-faint` bg, `--gruvax-blue-dark` border, `--gruvax-blue-dark` text |
| `reshuffle` | `RESHUFFLE` | `--gruvax-yellow-faint` bg, `--gruvax-blue-dark` border, `--gruvax-blue-dark` text |
| `csv` | `CSV IMPORT` | `--gruvax-blue-faint` bg, `--gruvax-blue` text |
| `yaml` | `YAML IMPORT` | `--gruvax-blue-faint` bg, `--gruvax-blue` text |

The yellow-tinted badges for `wizard` and `reshuffle` signals "this was a multi-cube wizard operation" — visually distinct from single-cube edits. This makes the Phase 3 undo keystone more legible when looking back at history.

---

### Surface 6: Nav Entry Points (Discretion)

**Where `/admin/wizard` and `/admin/import` live**

AdminShell nav bar (the existing `admin-topbar-nav`) gains two new tabs:

```
SETTINGS  CUBES  HISTORY  WIZARD  IMPORT
```

- Both new tabs use the same `admin-nav-tab` CSS class as existing tabs
- Active state: `admin-nav-tab--active` (existing class, unchanged)
- Tab order: WIZARD before IMPORT (wizard is the primary onboarding action; import is a secondary data-portability action)
- On mobile where the tab bar may overflow: the tabs wrap or scroll horizontally (same pattern used if screen is narrow — no truncation, no hamburger menu for admin tabs)

**Where boundaries export and settings export/import are surfaced**

Boundaries export (`GET /api/admin/export/boundaries.yaml`):
- Location: **`CubesGrid` view** (the shelf overview at `/admin/cubes`), below the shelf grid list, a secondary action row:
  - `EXPORT BOUNDARIES` — blue outline button, full-width on mobile, 44px min-height
  - Tap triggers the download directly (browser `<a href="…" download>` pattern)
  - No confirmation needed (export is read-only)

Settings export and settings import (`GET /api/admin/export/settings.yaml`, `POST /admin/import/settings`):
- Location: **`Settings.tsx` page** (`/admin/settings`), new section at the bottom with heading `BACKUP & RESTORE` (Barlow Condensed 700 16px ALL CAPS)
- Two actions side by side:
  - `EXPORT SETTINGS` — blue outline button, 44px min-height
  - `IMPORT SETTINGS` — blue outline button with file-input trigger, 44px min-height; tap opens file picker (accepts `.yaml`)
- Settings import shows an inline validation result (accepted keys list, then a `APPLY SETTINGS` confirm step or an error list for rejected keys)
- Settings import confirmation: inline within the Settings page (no separate route), showing `Settings applied.` in `--gruvax-success` color after successful PUT

---

## Copywriting Contract

All labels: ALL CAPS, Barlow Condensed 700. All instructions and body copy: sentence case, Space Grotesk 400.
Error messages: plain language, no technical jargon.

| Element | Copy | Notes |
|---------|------|-------|
| Primary CTA — wizard commit | `COMMIT ALL CHANGES` | Appears on wizard review step |
| Primary CTA — import commit | `COMMIT IMPORT` | Enabled only at zero errors |
| Primary CTA — wizard start (setup) | `START SETUP WIZARD` | Entry button on `/admin/cubes` or WIZARD tab |
| Primary CTA — wizard start (reshuffle) | `START RESHUFFLE` | Entry button on wizard route when existing boundaries present |
| Wizard step question | `What's the first record in this bin?` | Sentence case, Space Grotesk 400 16px |
| Wizard skip control | `THIS BIN IS EMPTY / SKIP` | ALL CAPS, Barlow Condensed 700 |
| Wizard end-of-shelf info | `This is the last bin. Everything in your collection from this point forward will be shelved here.` | Sentence case |
| Import file zone | `DROP A FILE OR TAP TO UPLOAD` | ALL CAPS, Barlow Condensed 700 |
| Import formats hint | `Accepts: .csv or .yaml` | Sentence case, 12px caption |
| Import partial warning | `This file defines [N] cubes. The remaining [M] cubes will be set to empty after import.` | Sentence case |
| Import movement count suffix | `(approx.)` | Appended to every non-zero movement count — REQUIRED per RESEARCH v1 caveat |
| Import error: phantom | `"[Label]" · "[Catalog]" — not found in your collection.` | DM Mono for the values |
| Import error: contiguity | `[Label] would be split across non-adjacent bins. Adjust this cut point to keep [Label] in one run.` | Plain language, no jargon |
| Import did-you-mean prompt | `Did you mean?` | Sentence case, Space Grotesk 400 14px |
| Resume banner heading | `RESHUFFLE IN PROGRESS — [N] OF [M] STEPS DONE` | ALL CAPS, dynamic |
| Resume banner sub-line | `Started [relative time] ago` | Sentence case |
| Resume banner action | `CONTINUE` / `DISCARD` | ALL CAPS |
| Discard confirm | `Are you sure? This will delete your in-progress reshuffle draft.` | Sentence case |
| Discard confirm yes | `YES, DISCARD` | ALL CAPS, destructive |
| Discard confirm no | `KEEP DRAFT` | ALL CAPS, neutral |
| Stale-draft warning | `Some records in your draft are no longer in the collection. Review the highlighted steps below.` | Sentence case |
| Confirmation heading — wizard setup | `BOUNDARIES COMMITTED` | ALL CAPS |
| Confirmation heading — reshuffle | `RESHUFFLE COMMITTED` | ALL CAPS |
| Confirmation heading — csv/yaml import | `IMPORT COMMITTED` | ALL CAPS |
| Confirmation operation sub-line | `Operation: [Wizard setup / Reshuffle / CSV import / YAML import] · [N] cubes` | Sentence case |
| Confirmation change_set_id label | `Change set` | Sentence case, 12px caption |
| Confirmation revert action | `REVERT THIS CHANGE SET` | ALL CAPS |
| Confirmation primary action | `BACK TO CUBES` | ALL CAPS |
| Settings import confirmation | `Settings applied.` | Sentence case, in --gruvax-success color |
| History badge — wizard | `WIZARD SETUP` | ALL CAPS |
| History badge — reshuffle | `RESHUFFLE` | ALL CAPS |
| History badge — csv | `CSV IMPORT` | ALL CAPS |
| History badge — yaml | `YAML IMPORT` | ALL CAPS |
| Export boundaries button | `EXPORT BOUNDARIES` | ALL CAPS |
| Export settings button | `EXPORT SETTINGS` | ALL CAPS |
| Import settings button | `IMPORT SETTINGS` | ALL CAPS |
| Settings backup section heading | `BACKUP & RESTORE` | ALL CAPS |
| Empty state — import (no file yet) | `Upload a CSV or YAML file to begin. All cubes not in the file will be set to empty.` | Sentence case |
| Empty state — wizard (no steps done) | The wizard immediately presents step 1 — there is no separate empty state. | — |
| Error state — wizard validate fail | `Something went wrong checking your changes. Check your connection and try again.` | Sentence case, Space Grotesk 400 14px |
| Error state — import commit fail | `Import failed — check your connection and try again. Your collection has not changed.` | Sentence case, plain language |
| Error state — settings import fail | `Settings could not be applied. Check that the file is a valid GRUVAX settings export.` | Sentence case |

### Destructive actions

| Action | Location | Confirmation approach |
|--------|----------|----------------------|
| DISCARD reshuffle draft | Resume banner | Inline two-step within the banner (no modal) — "Are you sure? This will delete your in-progress reshuffle draft." + YES, DISCARD / KEEP DRAFT |
| REVERT THIS CHANGE SET | Confirmation screen (post-commit) | Navigates to HistoryView with pre-opened confirm dialog for that change_set_id — reuses Phase 3 revert confirmation copy: "Revert this change set? This will restore the previous boundary values as a new, undoable change." |

---

## Component Inventory (what this phase builds vs reuses)

| Component | Status | File | Notes |
|-----------|--------|------|-------|
| `Wizard.tsx` | NEW | `frontend/src/routes/admin/Wizard.tsx` | Two-mode engine (setup/reshuffle), localStorage draft, step navigation |
| `Import.tsx` | NEW | `frontend/src/routes/admin/Import.tsx` | File upload, per-row error list, diff preview, commit |
| `ReshuffleBanner.tsx` | NEW | `frontend/src/routes/admin/ReshuffleBanner.tsx` | Resume/discard banner rendered by AdminShell |
| `ConfirmationScreen.tsx` | NEW | `frontend/src/routes/admin/ConfirmationScreen.tsx` | Post-commit confirmation, change_set_id display, revert tap |
| `LocatorHeader` | REUSED | existing | Extend with `totalSteps`, `completedSteps`, multi-shelf display |
| `RecordPickerSheet` | REUSED | existing | Used as wizard step input without modification |
| `HistoryView` | MODIFIED | existing | Source label map extended with 4 new source values |
| `AdminShell` | MODIFIED | existing | Add WIZARD + IMPORT nav tabs; mount ReshuffleBanner above Outlet |
| `CubesGrid` | MODIFIED | existing | Add EXPORT BOUNDARIES button at bottom of shelves list |
| `Settings.tsx` | MODIFIED | existing | Add BACKUP & RESTORE section at bottom |

Build constraint: all new components use `el()` + `replaceChildren()` DOM pattern (no `innerHTML`) matching the established project convention.

---

## Motion Contract

All transitions use existing animation tokens — no new keyframes.

| Interaction | Duration | Easing | Token |
|-------------|----------|--------|-------|
| Wizard step advance (content swap) | `--gruvax-duration-base` (250ms) | `--gruvax-ease-decelerate` | Slide-left exit + slide-in-right enter, or cross-fade on mobile |
| Wizard progress bar fill | `--gruvax-duration-fast` (150ms) | linear | Width CSS transition |
| LocatorHeader cell light-up | `--gruvax-led-on-duration` (300ms) | `--gruvax-led-on-ease` (spring) | LED-physics on-state |
| LocatorHeader cell dim | `--gruvax-led-off-duration` (500ms) | `--gruvax-led-off-ease` (smooth) | LED-physics off-state |
| Import commit button disabled→enabled | `--gruvax-duration-base` (250ms) | `--gruvax-ease-standard` | opacity + background-color |
| Resume banner appear | `--gruvax-duration-slow` (400ms) | `--gruvax-ease-decelerate` | Slide-down from top |
| Resume banner discard fade | `--gruvax-duration-base` (250ms) | `--gruvax-ease-accelerate` | Fade-out + collapse height |
| RecordPickerSheet slide-up | `--gruvax-duration-base` (250ms) | `--gruvax-ease-decelerate` | Existing pattern, unchanged |
| Confirmation screen appear | `--gruvax-duration-enter` (600ms) | `--gruvax-ease-decelerate` | Cross-fade from wizard/import content |
| Import error card appear | `--gruvax-duration-fast` (150ms) | `--gruvax-ease-decelerate` | Staggered fade-in per error card (10ms delay per card, max 200ms total) |
| change_set_id copy checkmark | 1500ms | hold, then instant revert | No animation — icon swap only |

General rule: UI feedback under 150ms (the `--gruvax-duration-fast` token), per the design language. Never animate for decoration.

---

## Registry Safety

No shadcn, no third-party component registries. Project uses vanilla DOM + existing internal components.

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | none | not applicable |
| npm packages | none new | no new packages introduced in Phase 7 (verified: RESEARCH.md §No New External Dependencies Required) |

---

## Checker Sign-Off

gsd-ui-checker, 2026-05-24 — **APPROVED, 0 blocking issues.** Three non-blocking FLAGs raised; two addressed in-spec, one accepted.

- [x] Dimension 1 Copywriting: FLAG (accepted) — `CONTINUE` / `DISCARD` are single-word CTAs; kept per CONTEXT.md D-07 ("Discard draft") and always rendered under the `RESHUFFLE IN PROGRESS — N OF M STEPS DONE` heading, so intent is unambiguous.
- [x] Dimension 2 Visuals: FLAG (fixed) — both icon-only controls (✕ clear-record, copy `change_set_id`) now carry explicit `aria-label`s.
- [x] Dimension 3 Color: PASS — 60/30/10 declared; accent reserved-for list is 6 specific elements; destructive color declared.
- [x] Dimension 4 Typography: FLAG (fixed/justified) — 4 weight values (400/500/700/900); each typeface capped at exactly 2 weights; 900 is display-only per locked Nordic Grid language. Justification added to Typography summary.
- [x] Dimension 5 Spacing: PASS — spacing scale tokens all in the standard set; cell-size tokens + 44px touch-floor are justified exceptions.
- [x] Dimension 6 Registry Safety: PASS — no shadcn, no third-party registries; vanilla DOM + design tokens only.

**Approval:** approved 2026-05-24 (0 blocking; FLAGs resolved/accepted)

---

## Pre-Populated From

| Source | Decisions Used |
|--------|---------------|
| `07-CONTEXT.md` | D-01 through D-15 (all 15 locked decisions — architecture, wizard modes, draft persistence, import semantics, confirmation, export schemas) |
| `07-RESEARCH.md` | Endpoint shapes (validate response schema, bulk request shape), component reuse map, movement-count approximation caveat, Idempotency-Key pattern, cut-point BoundaryEdit shape |
| `design/gruvax-design-tokens.css` | All spacing, typography, color, animation, shadow tokens |
| `design/gruvax-design-language.md` | Color semantics, typography roles, cell state specifications, accessibility rules |
| Sketch findings (`boundary-editing.md`) | Yellow=changed semantic, blue=structure, ↪=straddle, RecordPickerSheet/bin-card patterns, el()+replaceChildren() constraint |
| Existing components (`AdminShell.tsx`, `HistoryView.tsx`, `LocatorHeader.tsx`, `CubesGrid.tsx`) | Nav tab structure, source-label badge pattern, LocatorHeader props, existing CSS class patterns |
| `REQUIREMENTS.md` | ADMN-04, ADMN-05, ADMN-10, BAK-01, BAK-02 success criteria |
| This session (discretion decisions) | Confirmation surface (dedicated screen > toast), nav placement (WIZARD + IMPORT in top bar), export placement (boundaries in CubesGrid, settings in Settings), diff-preview mini-Kallax at md scale (40px cells), banner inline discard confirmation |

User questions asked this session: **0** — all design decisions were either locked in upstream artifacts or resolved from discretion items stated in CONTEXT.md.

---

*Phase: 07-wizards-import-export*
*UI-SPEC created: 2026-05-24*
*Researcher: gsd-ui-researcher (claude-sonnet-4-6)*

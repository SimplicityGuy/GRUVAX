# Phase 10: Shelf Fill-Overview - Context

**Gathered:** 2026-06-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Make the admin `LocatorHeader` mini 4×4 Kallax shade each cube by occupancy so the owner
sees how full each bin is at a glance — without opening the full boundary editor. This is
the **milestone-close phase** for v2.1 (single requirement: UX-01).

**This is a frontend-only visualization phase.** The backend data is already complete:
`GET /api/admin/cubes` returns `is_empty`, `fill_level` (0.0–1.0+), and `record_count` per
cube today (`src/gruvax/api/admin/cubes.py:166-218`). No new backend/endpoint work is
required for the fill data itself.

**In scope:** per-cube fill shading in `LocatorHeader`; live-refresh wiring; a tap-to-reveal
count popover.
**Out of scope:** changing how fill is computed; the full boundary editor; over-capacity
detection/alerts (owner still sees overflow in the editor); any kiosk-facing fill view
(UX-01 is admin-only).

</domain>

<decisions>
## Implementation Decisions

### Fill encoding (D-01 .. D-02)
- **D-01: Continuous BLUE-saturation gradient, not yellow.** Empty cubes render in the
  CUBE-05 desaturated state (`--gruvax-cell-empty`, gray + dashed border); fuller cubes get
  progressively deeper IKEA-blue saturation. **This is an intentional refinement of UX-01's
  wording "filled cubes proportionally lit"** — "lit" is read as *proportionally saturated
  blue*, NOT proportional yellow. Rationale: the Nordic Grid design language reserves yellow
  exclusively for active/changed/lit/LED state, and `LocatorHeader` already uses yellow for
  the "edited bin" highlight (`.locator-cell--lit`). Using yellow for occupancy would
  overload that meaning and collide with the edited-bin highlight. **Downstream agents must
  NOT "correct" this back to yellow to match the literal requirement text.**
- **D-02: Continuous gradient, not discrete buckets.** Map `fill_level` to a continuous blue
  shade (e.g. via `color-mix`/opacity derived from `--gruvax-blue` over the dim-blue base);
  do not quantize into low/med/high steps. Must remain glanceable at `--gruvax-cell-size-sm`
  (28px) on the 7" kiosk display, and an empty vs. full cube must be obviously distinct
  (UX-01 success criterion 3).

### Over-capacity (D-03)
- **D-03: Cap fill at full (clamp `fill_level` to 1.0 visually).** A bin over nominal
  capacity renders identically to an exactly-full bin (deepest blue) — no distinct
  over-capacity border, texture, or off-palette color. Keep it simple. The "bin is
  overflowing / time to reshuffle" signal is NOT surfaced in this glance view; the owner
  learns it from the full editor. (See Deferred Ideas.)

### Live refresh (D-04)
- **D-04: Invalidate the admin cubes query on BOTH `collection_changed` AND
  `boundary_changed`.** Shading must always match reality. A sync (nightly/manual) changes
  record counts; an admin boundary edit changes which records fall in each cube — both must
  reshade live with no page reload (UX-01 success criterion 2).
  - **Wiring note for planner:** the admin query key is `['admin','cubes']`
    (`ShelfBinList.tsx:84-85`). Today the SSE `collection_changed` handler is
    *kiosk-only* and invalidates kiosk keys (`['cubes']`, `['units']`, `['search']`) — per
    the D-08 comment it deliberately does NOT touch admin keys. `boundary_changed` likewise
    invalidates the kiosk `['cubes']` copy, not `['admin','cubes']`. `ShelfBinList` only
    invalidates `['admin','cubes']` after its *own* local mutations. So **both** event paths
    need new wiring to invalidate `['admin','cubes']` for fill to refresh from external
    sync/edits. Verify the SSE listener that's actually mounted on the admin route (the
    `KioskView` listeners at `KioskView.tsx:424-449` / `360-384` are kiosk-route).

### Glanceable detail (D-05 .. D-06)
- **D-05: Tap-to-reveal exact count.** `LocatorHeader` is non-interactive today (pure
  display). Add a tap affordance on each mini-cube. (Kiosk + admin are both touch / no hover,
  so this is tap, not hover.)
- **D-06: Reveal via an inline Nordic-Grid popover/tooltip**, self-contained in
  `LocatorHeader` — NOT scroll-to/highlight of the bin card. Tapping a cube shows something
  like `A1 · 47 records · 78%` (DM Mono for the numbers per the type system); dismiss on
  tap-away. An empty cube's popover shows an empty/0 state. Must not depend on the
  `ShelfBinList` cards below it.

### Claude's Discretion
- Exact CSS technique for the blue gradient (color-mix vs. layered opacity vs. computed
  custom property `--fill: <0..1>`), and the precise shade ramp endpoints — as long as it
  consumes design tokens (never hardcoded hex) and empty/full are clearly distinct at 28px.
- Popover positioning, anchor, and dismiss mechanics (tap-away, escape, re-tap).
- Whether the popover shows `%`, `record_count`, or both — D-06 suggests both; final exact
  string is open.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirement & roadmap
- `.planning/ROADMAP.md` — Phase 10 "Shelf Fill-Overview" entry: goal + 3 success criteria.
- `.planning/REQUIREMENTS.md` — **UX-01** (the sole requirement); names `is_empty` /
  `fill_level` from `GET /api/admin/cubes` and the CUBE-05 empty-cube state.

### Design language (MANDATORY — do not invent visuals)
- `design/gruvax-design-language.md` — Nordic Grid spec; yellow-reservation rule; CUBE-05
  empty state; type system (Barlow Condensed / Space Grotesk / DM Mono).
- `design/gruvax-design-tokens.css` — cube state tokens: `--gruvax-cell-empty` (CUBE-05
  desaturated), `--gruvax-cell-dim`, `--gruvax-cell-lit`, `--gruvax-blue`,
  `--gruvax-cell-size-sm` (28px), `--gruvax-cell-gap-sm`, `--gruvax-shadow-led`.
- `.claude/skills/sketch-findings-gruvax/SKILL.md` — validated Nordic Grid direction;
  "yellow is exclusively active/changed/lit"; compact 4×4 mini-Kallax locator.

### Backend data source (read-only for this phase)
- `src/gruvax/api/admin/cubes.py:166-218` — `GET /api/admin/cubes` handler; returns
  `unit_id`, `row`, `col`, `first_label`, `first_catalog`, `is_empty`, `fill_level`,
  `record_count`. Fill computed via `count_records_in_bin()` over `SegmentCache.get_bin()`.
- `src/gruvax/estimator/boundary_math.py` — `count_records_in_bin()`.
- `src/gruvax/estimator/segment_cache.py` — `SegmentCache`, `SegmentBin` (record-count source).

### Frontend touch points
- `frontend/src/routes/admin/LocatorHeader.tsx:1-64` — the component to modify. Renders the
  4×4 mini-Kallax; cells `.locator-cell--lit` / `--dim`; uses `--gruvax-cell-size-sm`.
- `frontend/src/routes/admin/ShelfBinList.tsx:1-276` — hosts `LocatorHeader` (passes
  `row=-1,col=-1`); fetches cubes via `adminGetCubes()` / key `['admin','cubes']`
  (lines 84-93); invalidates `['admin','cubes']` + `['admin','segments',unitId]` after local
  edits.
- `frontend/src/routes/kiosk/KioskView.tsx:360-384, 424-449` — existing SSE
  `boundary_changed` / `collection_changed` handlers (kiosk route) — reference patterns for
  the admin-side invalidation wiring.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `LocatorHeader.tsx` already renders the 4×4 mini-Kallax grid and consumes the small-size
  cube tokens — the fill work is *adding per-cell state*, not building a new grid.
- The `AdminCube` frontend type already flows from `adminGetCubes()`; it must be updated to
  carry `record_count` (and confirm `fill_level` / `is_empty`) — scout flagged it as stale
  (still references removed `last_label`/`last_catalog`).
- `ShelfGrid.tsx` (kiosk) demonstrates a `fillLevels`-style prop + per-cell state pattern
  worth mirroring for `LocatorHeader`.
- Existing `recentlyChanged` highlight pattern in `ShelfBinList` (not used for D-06, but the
  app's animation idiom).

### Established Patterns
- Design tokens only — never hardcode hex (CLAUDE.md + design language).
- SSE-driven TanStack Query invalidation is the app's live-update idiom; admin vs. kiosk
  query keys are deliberately separated (D-08).
- Vanilla type system: DM Mono for numeric/catalog data (popover counts).

### Integration Points
- `GET /api/admin/cubes` → `['admin','cubes']` query → `ShelfBinList` → `LocatorHeader` props.
- The admin-route SSE listener (wherever it is mounted) → invalidate `['admin','cubes']` on
  `collection_changed` and `boundary_changed`.

</code_context>

<specifics>
## Specific Ideas

- Popover example string: `A1 · 47 records · 78%` (DM Mono numerals).
- Gradient mental model captured in discussion: `░ empty → ▒ ~30% → ▓ ~70% → █ full`, blue
  family, with the edited-bin **yellow** highlight kept strictly separate.

</specifics>

<deferred>
## Deferred Ideas

- **Over-capacity surfacing in the glance view** — a distinct visual for `fill_level > 1.0`
  (over-cap border / texture / warning). Explicitly cut from this phase (D-03 caps at full).
  Candidate for a future "reshuffle suggestions" enhancement; pairs naturally with the
  existing reshuffle wizard (v1.0 Phase 7).
- **Tap-cube → jump to bin card** (the scroll-to/highlight alternative to D-06's popover) —
  could be a later convenience if the popover proves limiting.

None of the above is in scope for Phase 10.

</deferred>

---

*Phase: 10-Shelf-Fill-Overview*
*Context gathered: 2026-06-02*

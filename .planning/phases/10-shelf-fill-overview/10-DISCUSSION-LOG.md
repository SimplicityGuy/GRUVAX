# Phase 10: Shelf Fill-Overview - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-02
**Phase:** 10-Shelf Fill-Overview
**Areas discussed:** Fill encoding, Over-capacity signal, Live-refresh triggers, Glanceable detail

---

## Fill encoding

| Option | Description | Selected |
|--------|-------------|----------|
| Blue saturation gradient | Empty = desaturated gray (CUBE-05); fuller = deeper IKEA-blue. Keeps yellow free. | ✓ |
| Partial-height fill bar | Bottom-up liquid/battery gauge; hard to read at 28px. | |
| Proportional yellow (literal UX-01) | Brighter yellow = fuller; overloads the reserved yellow. | |
| Discrete buckets | 3–4 fixed steps; coarser but glanceable. | |

**User's choice:** Blue saturation gradient (continuous).
**Notes:** Intentional refinement of UX-01's "proportionally lit" → proportionally saturated
blue, to honor the Nordic Grid yellow-reservation rule and avoid colliding with the existing
yellow edited-bin highlight. Planner must not revert to yellow. Followed up to confirm
continuous gradient over discrete buckets.

---

## Over-capacity signal

| Option | Description | Selected |
|--------|-------------|----------|
| Distinct over-cap border | Cap blue at full, add inset/double ring for >100%. | |
| Just cap at full | Clamp fill_level to 1.0; over-full looks identical to full. | ✓ |
| Hatch / texture overlay | Diagonal-hatch on over-cap cubes; noisy at 28px. | |

**User's choice:** Just cap at full.
**Notes:** Overflow/reshuffle signal stays in the full editor; not surfaced in the glance
view. Distinct over-cap visual noted as a deferred idea.

---

## Live-refresh triggers

| Option | Description | Selected |
|--------|-------------|----------|
| Both sync + boundary edits | Invalidate `['admin','cubes']` on collection_changed AND boundary_changed. | ✓ |
| Sync only (collection_changed) | Literal UX-01; boundary edits lag until next refetch. | |

**User's choice:** Both sync + boundary edits.
**Notes:** Shading should always match reality. Flagged that `collection_changed` is
kiosk-only today and neither event currently invalidates `['admin','cubes']` from external
changes — both need new wiring.

---

## Glanceable detail

| Option | Description | Selected |
|--------|-------------|----------|
| Purely visual (no reveal) | Shading is the only info; counts live in cards below. | |
| Tap to reveal count | Tapping a cube surfaces record_count / %. | ✓ |
| Always-on count label | DM Mono number in each cube; too small at 28px. | |

**User's choice:** Tap to reveal count.

### Reveal mechanism (follow-up)

| Option | Description | Selected |
|--------|-------------|----------|
| Inline popover/tooltip | Self-contained popover in LocatorHeader (e.g. `A1 · 47 records · 78%`), dismiss on tap-away. | ✓ |
| Scroll to + highlight bin card | Tap scrolls ShelfBinList to the matching card and flashes it. | |

**User's choice:** Inline popover/tooltip.
**Notes:** Self-contained in LocatorHeader; no dependency on the bin-card list. Empty cube
shows an empty/0 state. DM Mono for numerals.

---

## Claude's Discretion

- Exact CSS technique for the blue gradient and the shade ramp endpoints (token-driven only).
- Popover positioning / dismiss mechanics; exact reveal string (% vs count vs both).

## Deferred Ideas

- Over-capacity surfacing in the glance view (distinct visual for fill_level > 1.0) — pairs
  with a future reshuffle-suggestions enhancement.
- Tap-cube → jump to bin card (the scroll-to alternative) as a later convenience.

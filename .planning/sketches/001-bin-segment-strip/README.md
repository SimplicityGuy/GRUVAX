---
sketch: 001
name: bin-segment-strip
question: "How does the owner read a bin's per-label split and drag to set physical-width overrides, on a phone?"
winner: "A"
tags: [segments, drag, override, mobile, phase-5]
---

# Sketch 001: Bin Segment Strip

## Design Question

A Kallax bin holds an ordered list of per-label segments. The count-derived fraction
(from `v_collection` row counts) is the default, but the owner can set a **physical-width
override** when the shelf reality diverges. How should that read and edit on a phone —
including the **count-default vs override** distinction and the **straddle** case where a
label continues into the next bin?

## How to View

```
open .planning/sketches/001-bin-segment-strip/index.html
```

Use the toolbar (bottom-right) to switch phone / tablet / desktop widths. State is shared
across all three tabs — drag in A, then check B and C reflect the same numbers.

## Variants

- **A — Strip + drag** — one horizontal proportional bar, segments in graduated IKEA-blues,
  drag the handles between segments to set an override. Overridden segments get a yellow
  LED-glow top edge; the straddle segment fades out with an `↪`. Legend below (on white)
  carries the contrast-sensitive detail: catalog range, `AUTO 46% from row counts` vs
  `OVERRIDE 45% · auto was 46%` with a one-tap reset.
- **B — Vertical stack** — same data stacked top→bottom in shelf order, height-proportional
  bands with full label + catalog range inside each. Handles are horizontal bars between
  bands — the most thumb-reachable on a tall phone. Straddle band shows `↪ continues in bin 2`.
- **C — Strip + numbers** — a compact read-out strip plus DM-Mono percentage steppers per
  label. Typing an exact value re-balances the others proportionally to keep the sum at 100%.
  For the owner who wants to dial in a precise split rather than eyeball a drag.

## What to Look For

- **Does the override vs auto distinction read instantly?** Yellow = "you changed this"
  everywhere; blue family = structure. Is that legible, or too subtle?
- **Drag feel** — handle size, the live width reflow, whether 100%-conservation feels natural.
- **The straddle treatment** — is `↪ continues in bin 2` clear enough that the owner trusts
  the label isn't being truncated, just continued?
- **Thumb reach on phone** (default 390px) — A's vertical handles vs B's horizontal handles.
- **Color discipline** — yellow is reserved for active/changed/lit per the design language;
  segments stay in the blue family. Does that hold up with 3–4 segments?

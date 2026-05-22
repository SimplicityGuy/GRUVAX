---
sketch: 002
name: cut-point-editor
question: "How does the owner view, edit, and add cut points (splitting one bin into two)?"
winner: "A"
tags: [cut-points, editing, split, mobile, phase-5]
---

# Sketch 002: Cut-Point Editor

## Design Question

A cut point is the first record of a bin — the single input the owner maintains, from which
all segments derive. The owner needs to **view** the ordered cuts, **edit** a cut's first
record, and **add** a cut (split one bin's range into two, which renumbers later bins). How
should that read and operate on a phone, cohesive with Sketch 001's segment language?

## How to View

```
open .planning/sketches/002-cut-point-editor/index.html
```

Try: tap ✎ to edit a cut (a record picker slides up — note the dupes/variants like
`AS 78` 2nd copy and `AS 78-r` remix, reinforcing "counts come from rows, not arithmetic").
Tap **＋ insert cut** / **＋ add cut** to split a bin — watch the renumber hint and the
new yellow bin appear. In B, drag a cut line up/down to move a boundary.

## Variants

- **A — Bin list + insert** — vertical list of bin cards, each showing its cut point
  (`starts at LABEL · record`) plus a mini segment strip echoing Sketch 001. A dashed
  **＋ insert cut** divider sits between every pair of bins. Most legible; reuses the
  winning 001 visual language directly.
- **B — Record spine** — a timeline of bins and their records; cut lines are blue chips you
  **drag** to move a boundary, with **＋ add cut here** in each gap. The most spatial /
  tactile take — feels like scrubbing the boundary along the record sequence.
- **C — Cut table** — a dense DM-Mono table (Bin · First record · Label · edit) with a single
  prominent **＋ Add cut · split a bin**. The fastest, most utilitarian; best when the owner
  knows exactly what to change and wants minimal chrome.

All three share one **record picker** sheet (faked autocomplete) and the **renumber hint**
that appears when adding a cut.

## What to Look For

- **Is "add cut = split a bin" obvious**, and is the renumber consequence clear enough that
  the owner isn't surprised when later bins shift?
- **Cohesion with 001** — does A's mini-strip make the two screens feel like one tool?
- **Edit gesture** — does the slide-up record picker feel right for a phone, and do the
  dupe/variant rows make the "row counts" reality legible?
- **B's drag** — does moving a cut along the spine feel trustworthy, or too easy to fat-finger?

# Sketch Manifest

## Design Direction

Admin UI for GRUVAX's **segment-aware boundary model** (Phase 5). A Kallax bin holds
an *ordered list of per-label segments*; the owner maintains boundaries by setting
**cut points** (the first record of each bin) and, where physical reality diverges from
the count-derived split, dragging **physical-width overrides** for the labels inside a
bin. Everything is rendered in the **Nordic Grid** design language (IKEA-blue structure,
yellow reserved for lit/active/changed, Barlow Condensed ALL-CAPS labels, Space Grotesk
UI body, DM Mono for catalog numbers and percentages). **Mobile-first** — the admin is a
phone-held tool. The Kallax cube remains the atomic locating unit.

## Reference Points

- GRUVAX design language (`design/gruvax-design-language.md`) — mandated, not optional.
- IKEA price-tag / Kallax visual system (institutional blue, condensed type).
- Stacked-proportional bar charts; iOS-style drag handles for the override interaction.
- Design rationale + data model: `.planning/notes/segment-aware-boundaries.md`.

## Sketches

| # | Name | Design Question | Winner | Tags |
|---|------|----------------|--------|------|
| 001 | bin-segment-strip | How does the owner read a bin's per-label split and drag to set physical-width overrides, on a phone? | **A · Strip + drag** | segments, drag, override, mobile |
| 002 | cut-point-editor | How does the owner view, edit, and add cut points (splitting one bin into two)? | _pending 001_ | cut-points, editing, mobile |

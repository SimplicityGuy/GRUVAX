# Phase 5: Segment-Aware Position Precision - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-22
**Phase:** 5-segment-aware-position-precision
**Areas discussed:** Estimator cutover & A/B proof, Override drift & lifecycle, Bin renumber & identity, Big labels: multi-bin span

---

## Estimator cutover & A/B proof

### Acceptance bar (SEG-07)
| Option | Description | Selected |
|--------|-------------|----------|
| Win multi-label, tie single | Strictly better on multi-label/straddle shapes + parity within noise on single-label | ✓ (later mooted) |
| Strictly ≥ every shape | Never worse on any tested distribution shape | |
| ≥ aggregate, small ties OK | Overall MAE beats §4.1, small per-shape ties allowed | |

### Keep §4.1? (cutover)
| Option | Description | Selected |
|--------|-------------|----------|
| Retire from prod, keep in harness | Segment-aware sole index estimator; §4.1 only as harness baseline | |
| Keep §4.1 selectable in prod | Three selectable algorithms | |
| **Other (free text)** | **"Retire the old estimate entirely. No A/B proof needed"** | ✓ |

### A/B proof reconciliation (conflict surfaced by Claude)
| Option | Description | Selected |
|--------|-------------|----------|
| Informational, not a gate | Retire §4.1; extend harness as a report + regression guard, not a release gate | |
| Keep proof as a hard gate | Original SEG-07: harness gates the cutover | |
| Drop the harness entirely | No multi-label/straddle shapes, no comparison; ship segment-aware on trust | ✓ |

**User's choice:** Retire §4.1 entirely; **drop the A/B comparison harness entirely**; ship the
segment-aware estimator on trust.
**Notes:** Claude flagged that this conflicts with the acceptance-bar + harness-shape picks and
with SEG-07 / ROADMAP criterion 4 (which mandate the proof before cutover), and that it removes the
regression safety net. Owner confirmed the descope with full awareness of the tradeoff. Captured as
**D-01** (amends SEG-07, relaxes ROADMAP criterion 4); the acceptance-bar and harness-shape
selections are now moot. Correctness/property tests are still required (**D-02**).

---

## Override drift & lifecycle

### Drift policy (SEG-04)
| Option | Description | Selected |
|--------|-------------|----------|
| Flag drift, offer re-sync | Yellow review hint + one-tap resync when override diverges from auto; never auto-change | ✓ |
| Stay silent, show auto | Override wins; just show current auto in the legend | |
| Auto-clear on big drift | Discard override when drift exceeds a threshold | |

### Orphaned-override lifecycle
| Option | Description | Selected |
|--------|-------------|----------|
| Drop + report in diff | Remove orphaned override, surface in the Phase 3 diff-preview, ride change-set undo | ✓ |
| Migrate to where label moved | Follow the label across bins | |
| You decide | Delegate to planner | |

**User's choice:** Flag drift with one-tap re-sync (never auto-change); drop orphaned overrides and
report them in the diff-preview.
**Notes:** Captured as **D-03** and **D-04**. Builds on the sketch's existing `OVERRIDE · auto was`
+ reset affordance.

---

## Bin renumber & identity

### Bin ↔ physical cube
| Option | Description | Selected |
|--------|-------------|----------|
| 1:1 with a physical cube | Bin IS a cube; cut point = first record, "last" derived; durable id = (unit,row,col) | ✓ |
| Logical partition over cubes | Bins are a logical layer mapped onto cubes separately | |
| You decide | Delegate | |

### Insert / renumber mechanics (SEG-08)
| Option | Description | Selected |
|--------|-------------|----------|
| Cascade as one change-set; IDs durable | Insert cascades subsequent cut points in one change-set; overrides/history/LED maps attach to durable (unit,row,col) and survive | ✓ |
| Bin number is the identity | References stored by ordinal bin number, rewritten on renumber | |
| You decide | Delegate | |

**User's choice:** Bin = physical cube 1:1; insert cascades subsequent cut points as one
change-set with durable IDs surviving the renumber.
**Notes:** Captured as **D-05** and **D-06**. Preserves Phase 1–3 `cube_boundaries` continuity and
protects Phase 6 LED mapping. Claude flagged the end-of-shelf cut-insert overflow edge for the
planner.

---

## Big labels: multi-bin span

### Owner knowledge
| Option | Description | Selected |
|--------|-------------|----------|
| No — 1 cube, sometimes 2 | ≤2-bin assumption holds | |
| Yes — some span 3+ | A label crosses multiple cuts | |
| Not sure | Build for the general case | ✓ |

### Generality
| Option | Description | Selected |
|--------|-------------|----------|
| Generic (handles N for free) | Compare rank to all cut points splitting the label; straddle UI shows one ↪ per crossed cut | ✓ |
| Hard-cap at 2 | Validator rejects labels spanning 3+ bins | |
| You decide | Delegate | |

**User's choice:** Build the estimator generically for N adjacent bins; straddle UI chains one ↪
per crossed cut; contiguity invariant rejects only non-adjacent scattering.
**Notes:** Captured as **D-08** and **D-09**. Owner unsure of largest label, so general case is the
safe default at near-zero cost.

---

## Claude's Discretion

- Exact drift threshold for the override "review" hint.
- Save-validation taxonomy (hard-reject vs warn) + plain-language contiguity/empty-bin/phantom messaging.
- End-of-shelf cut-insert overflow behavior.
- Migration mechanics for `cube_boundaries` → cut-point model (Alembic round-trip; drop vs derive `last_*`).
- Where/when derived segments are computed + cached (reuse boundary cache + snapshot + Phase 4 invalidation).
- All exact visual/interaction polish → `/gsd-ui-phase 5`.

## Deferred Ideas

- A/B comparison harness for the segment estimator — **descoped, not deferred** (D-01).
- Physical LED sub-span lighting — Phase 6.
- Bulk reshuffle / guided wizard + CSV/YAML import/export — Phase 6.
- Format-thickness sub-segment weighting — future.
- Owner-curated real golden positions — post-reshuffle (Phase 6).

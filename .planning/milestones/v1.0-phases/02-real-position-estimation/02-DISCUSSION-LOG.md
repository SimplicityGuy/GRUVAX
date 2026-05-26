# Phase 2: Real Position Estimation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-20
**Phase:** 2-real-position-estimation
**Areas discussed:** Position bar & confidence, Span highlight & animation, Estimator accuracy & truth, Search refinements

---

## Position bar & confidence

### Low-confidence sub-cube bar behavior
| Option | Description | Selected |
|--------|-------------|----------|
| Attenuate by confidence | Always show a bar; scale intensity/glow (and optionally width) with confidence (§5.3 spirit) | ✓ |
| Threshold gate → cube-only | Crisp bar above a threshold; below it, drop the bar and highlight the whole cube | |
| Fixed prominence always | Same prominence regardless of confidence | |

**User's choice:** Attenuate by confidence

### Singleton rendering (CUBE-10)
| Option | Description | Selected |
|--------|-------------|----------|
| Centered tick mark | Tick at cube center (f=0.5 convention, §6) | |
| Full-cube faint band | Faint band spanning the whole cube — "the cube is the answer" | ✓ |
| Cube highlight only | No tick/band; just the primary-cube highlight | |

**User's choice:** Full-cube faint band
**Notes:** Reinterprets CUBE-10's literal "tick-mark" wording → flagged in CONTEXT D-02 for planner reconciliation; consistent with the attenuate-by-confidence choice (singleton = lowest confidence).

### Surface uncertainty in words/iconography?
| Option | Description | Selected |
|--------|-------------|----------|
| Purely visual | Confidence communicated only through bar/band rendering | |
| Subtle text cue on low conf | "approx."/"~" only below the cube-only threshold | ✓ |
| You decide (defer to UI phase) | Capture intent, let /gsd-ui-phase resolve | |

**User's choice:** Subtle text cue on low conf

---

## Span highlight & animation

### Multi-cube span highlight relationship to primary (CUBE-03)
| Option | Description | Selected |
|--------|-------------|----------|
| Subordinate backdrop | Spanned cubes get a dimmer ambient glow behind the bright primary | |
| Outline-only span | Spanned cubes get a border/outline; only primary filled | |
| Connecting underlay | A band/connector under the spanned cubes linking them; primary lit on top | ✓ |

**User's choice:** Connecting underlay
**Notes:** New visual element → CONTEXT D-04 flags it must not recolor a lit cell and must handle row/unit wrap; design detail deferred to /gsd-ui-phase 2.

### ≤600ms lands animation feel (CUBE-08)
| Option | Description | Selected |
|--------|-------------|----------|
| Sequential cinematic | Span fade-in → primary pulse/spring → sub-cube bar slide-in | ✓ |
| Near-simultaneous snappy | Everything springs in together (~150–250ms) | |
| You decide (defer to UI phase) | Lock budget + interruptibility, defer staging | |

**User's choice:** Sequential cinematic

### Interruption on new search mid-animation
| Option | Description | Selected |
|--------|-------------|----------|
| Hard cancel + restart | Snap old off, start new animation fresh | ✓ |
| Graceful cross-fade | Cross-fade old out as new comes in | |

**User's choice:** Hard cancel + restart

---

## Estimator accuracy & truth

### A/B harness ground-truth source (POS-06)
| Option | Description | Selected |
|--------|-------------|----------|
| Synthetic w/ planted truth | Generator places records at known positions across controlled shapes; measures §4.1 vs §4.8; CI-gated; real validation deferred | ✓ |
| Hand-curate ~20 real now | Owner hand-curates real shelf positions this phase | |
| Rank-proxy only | Normalized-rank as truth (can't truly validate §4.1) | |

**User's choice:** Synthetic w/ planted truth
**Notes:** Boundaries are still fixtures (no real reshuffle yet) → success criterion 5 reframed/softened in CONTEXT D-08; real-shelf validation deferred to post Phase 3/6.

### Physical shelf spacing within a label (§8.1 Q1)
| Option | Description | Selected |
|--------|-------------|----------|
| Uniform / packed | Records packed in catalog order regardless of gaps — index = position (§4.1) | ✓ |
| Density / gapped | Physical gaps reflect catalog spacing (§4.10 would matter) | |
| Not sure yet | Assume uniform, revisit with A/B harness | |

**User's choice:** Uniform / packed
**Notes:** Confirms §4.1 is correct; §4.10 stays deferred.

### Multi-prefix label arrangement (§8.1 Q2)
| Option | Description | Selected |
|--------|-------------|----------|
| Grouped by prefix | All BLP, then all BST (prefix-first) — matches Phase 1 parser | ✓ |
| Interleaved by number | Sorted by number across prefixes — parser would need adjustment | |
| Not sure / verify later | Assume grouped, verify in reshuffle wizard | |

**User's choice:** Grouped by prefix
**Notes:** Validates the Phase 1 Strategy-C parser sort; no parser change needed.

### Multi-label record shelving (§8.1 Q4)
| Option | Description | Selected |
|--------|-------------|----------|
| Under first label | First label listed, matches CSV/Discogs order | ✓ |
| Most-prominent label | Whichever label is prominent on the pressing (manual) | |
| Not sure / verify later | Assume first-label, revisit | |

**User's choice:** Under first label

---

## Search refinements

### Did-you-mean presentation (SRCH-07)
| Option | Description | Selected |
|--------|-------------|----------|
| Inline suggestion row | Single tappable "Did you mean X?" row in/above no-results | ✓ |
| Auto-correct w/ note | Silently run corrected query with an undo | |
| Short suggestion list | Up to ~3 candidate corrections | |

**User's choice:** Inline suggestion row

### Did-you-mean aggressiveness
| Option | Description | Selected |
|--------|-------------|----------|
| Conservative | High trigram-similarity only when FTS returns nothing strong | ✓ |
| Moderate | Suggest more readily, including when weak results exist | |
| You decide | Pick a default threshold, tune against the CSV | |

**User's choice:** Conservative

### Catalog-# boost detection breadth (SRCH-08)
| Option | Description | Selected |
|--------|-------------|----------|
| Leading-digit + prefix+digits | Boost on "4195" OR "BLP 41"-style queries | ✓ |
| Leading-digit only | Boost only when query starts with a digit | |
| You decide | Let planner choose, informed by CSV formats | |

**User's choice:** Leading-digit + prefix+digits

---

## Claude's Discretion

- Confidence calibration numbers for §4.1 (per-shape formula; cube-only/text-cue threshold) — INTERPOLATION §5.1/§8.2.
- In-memory collection snapshot design (startup load alongside boundary cache; POS-03 no-DB-during-compute).
- `estimator_version` tag for §4.1 and the §4.8 fallback-selection path.
- `pg_trgm` availability confirmation on the shared Postgres (SRCH-07 dependency).
- Did-you-mean similarity threshold + FTS ranking weights, tuned against the local CSV.
- All exact visual/motion design → /gsd-ui-phase 2 within the design system.

## Deferred Ideas

- §4.10 density-weighted interpolation — fast-follow only if §4.1 feels off on sparse labels (owner shelves uniform → deferred with confidence).
- Owner-curated real golden positions — produce after a real reshuffle (Phase 3/6) to close the D-08 validation loop.
- Tiered cascade (§5.1) + monotone safety net (§5.2) — post-v1 once A/B per-shape error bars are visible.
- Real-shelf validation of multi-prefix grouping + multi-label assumptions — verify by eye in the Phase 6 reshuffle wizard.
- KNN (§4.5), isotonic (§4.9), precomputed lookup table (§4.7) — explicit hard-no for v1.

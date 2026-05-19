# Position-Estimation Research — GRUVAX

**Domain:** Sub-cube position estimation for a record's physical location on a deterministically ordered shelf. One record → `(primary_cube, label_span, sub_cube_interval, confidence)`.
**Researched:** 2026-05-18
**Confidence:** HIGH on aggregate statistics from the local collection CSV (computed directly). HIGH on the catalog-number parsing taxonomy. MEDIUM on per-algorithm accuracy claims — accuracy depends on the user's actual shelf layout, which is data we don't yet have. The right way to *pick* an algorithm is empirical: build the test harness described in §7, run candidates against the real CSV, and let the numbers decide.

This document does **not** prescribe a winning algorithm. It presents a comparative survey calibrated to the *actual* distribution of the user's collection, the locked contract from `ARCHITECTURE.md`, and the catalog-number normalization rules implied by `PITFALLS.md` Pitfall 1.

---

## 1. Problem Framing & Contract Recap

The position estimator answers a single question: *given a `release_id`, where on the shelves is it?* The answer has two parts:

1. **Label-span** — the set of cubes the record's `Label` occupies in the user's hand-sorted arrangement. Cardinality is almost always 1 (see §2 — no label is large enough to fill a cube on its own); occasionally 2 when a label happens to straddle a cube boundary.
2. **Sub-cube position interval** `[start, end] ∈ [0, 1]²` — a normalized horizontal slice *within the primary cube* where the specific record likely sits. The interval may cross a cube boundary (in which case `crosses_boundary=true` and `next_cube` is populated).

Per `ARCHITECTURE.md` §Position-Estimator Contract:
- Input: `release_id` (int).
- Output: `LocateResult{primary_cube, label_span: list[CubeRef], sub_cube_interval: SubInterval | None, confidence: float, generated_at, estimator_version}`.
- Latency: estimator ≤ 50 ms p95, CPU-only, no DB calls during computation. Boundaries pre-loaded into an in-memory cache, invalidated by `boundary_changed` events.
- Error semantics: 404 for not-in-collection; `confidence: 0.0` with `primary_cube: null` for no covering boundary; timeout fallback returns boundary-lookup-only with `sub_cube_interval: null`.

What the algorithm decides: label normalization, catalog-number comparison, interpolation method, confidence formula. What it doesn't decide: contract shape, latency budget, error semantics.

The estimator's inputs at compute time:

- A pre-loaded `cube_boundaries` array (≤ 32 rows): each row holds `(unit_id, row, col, first_label, first_catalog, last_label, last_catalog)`.
- The queried record's `(label, catalog_number)` (resolved upstream from `release_id`).
- *Optionally* a pre-loaded snapshot of `v_collection` rows (the user's owned records) — required by some candidates (CDF, nearest-neighbor) and not by others (linear, anchored). Trade-off discussed per-candidate in §4.

Pitfall 1 from `PITFALLS.md` is binding: catalog-number comparison must go through a normalization layer (case-fold, separator collapse, numeric-aware split), *not* raw string comparison. The same normalization is applied to both the boundary row and the queried record. §3 expands this into a catalog-parsing taxonomy.

---

## 2. Distribution of the Real Collection

All statistics below are computed from the local Discogs export (`RWlodarczyk-collection-20260519-0257.csv`, 3,030 records, gitignored). **No row content is reproduced in this document.** Examples in later sections use illustrative-but-synthetic catalog numbers.

### 2.1 Records and labels

| Metric | Value |
|---|---|
| Total records | 3,030 |
| Unique label strings (as stored in the `Label` column) | 1,215 |
| Records per label, mean | 2.49 |
| Records per label, median | **1** |
| Records per label, max | 51 |
| Average records per cube (at N=32 cubes) | ~95 |

### 2.2 Label-size distribution

| Label size | # labels | % of labels | Records | % of records |
|---|---:|---:|---:|---:|
| 1 (singleton) | 805 | 66.3% | 805 | 26.6% |
| 2 | 182 | 15.0% | 364 | 12.0% |
| 3 | 63 | 5.2% | 189 | 6.2% |
| 4–5 | 61 | 5.0% | ~265 | 8.8% |
| 6–10 | 61 | 5.0% | ~449 | 14.8% |
| 11–20 | 24 | 2.0% | ~352 | 11.6% |
| 21–50 | 18 | 1.5% | ~554 | 18.3% |
| 51–100 | 1 | 0.1% | 51 | 1.7% |
| 100+ | 0 | 0.0% | 0 | 0.0% |

**Key implication:** Because the largest label has 51 records while a cube holds ~95 on average, **no single label is big enough to fill even one cube**. Therefore:

- Every label fits within at most one *interior* of a cube plus, possibly, a sliver of the adjacent cube. A label's `label_span` is **1 cube ~90% of the time, 2 cubes ~10% of the time, and ≥3 cubes effectively never** (under a uniform-shuffle assumption; the real number may be lower because labels tend to be packed contiguously).
- Sub-cube interpolation is the dominant complexity, not multi-cube spans.
- A massive class of queries — the ~27% of records that are the *only* record from their label — collapses to a degenerate case: span = 1 cube, sub-cube interval may legitimately be the entire cube width (or a small fixed window around the cube's midpoint), confidence = a special "singleton" value.

### 2.3 Catalog-number format distribution

Of 3,030 records, 2,983 have a non-empty, non-placeholder catalog number; 47 (1.6%) use the Discogs `none` marker or equivalent. 3 records (0.1%) contain no digit at all (pure-alpha catalog).

| Structural shape | Count | % |
|---|---:|---:|
| alpha-prefix then digits (`ABC123`, `BLP 4195`) | 1,881 | 63.1% |
| other / mixed (multi-segment, dotted, slashed) | 494 | 16.6% |
| pure numeric (`32731`) | 296 | 9.9% |
| alpha-digits-alpha (`ABC123XY`) | 200 | 6.7% |
| digits-alpha-digits (`9NUM005`-shape) | 65 | 2.2% |
| digits-then-alpha (`123ABC`) | 47 | 1.6% |

| Alpha-case pattern | Count | % |
|---|---:|---:|
| ALL UPPER (`BLP`) | 2,284 | 76.6% |
| no alpha (numeric only) | 331 | 11.1% |
| all lower (`cat`) | 203 | 6.8% |
| Mixed_or_camel (`McA`, `iN`) | 80 | 2.7% |
| Title Case (`Wraith`) | 85 | 2.8% |

| Separator usage (per catalog#) | Count |
|---|---:|
| space only | 1,130 |
| no separator | 932 |
| space and dash mixed in same string | 427 |
| dash only | 416 |
| period only | 24 |
| other combinations | < 50 |

**Multi-value catalog fields** (comma-separated within a single row, e.g., a release with multiple catalog numbers issued by the label): 394 records (13.0%), of which 370 have exactly two parts. The estimator must decide which part is canonical for sort purposes; "first part" is a reasonable default but should be flagged as a deliberate design choice in normalization.

**Multi-label rows** (the `Label` field itself contains commas — releases co-issued by multiple labels): 573 records (18.9%). The estimator's `label` key is the *raw* Label string per Discogs and per the user's sort convention; splitting it apart would re-sort records the user has not asked to re-sort. Validation tests should pin this.

### 2.4 Format consistency *within* a label

Restricting to the 405 multi-record labels (the only ones for which "consistency" is meaningful):

| Property | # labels affected | % of multi-record labels |
|---|---:|---:|
| Mixed alpha case across that label's catalog#s | 86 | 21.2% |
| Mixed separators across that label's catalog#s | 168 | **41.5%** |
| Multiple alpha-prefix families within one label (e.g., `BLP` + `BST` style) | 141 | 34.8% |
| Varying digit-run lengths across that label's catalog#s | 142 | 35.1% |
| Raw-string sort order ≠ numeric-aware sort order | 144 | **35.6%** |

**The "35.6% disagreement" number is the single most important signal in this entire research.** It is the empirical floor on Pitfall 1's blast radius: more than a third of multi-record labels would be sorted *wrong* by raw-string comparison alone. A correct sort key is not a refinement, it is a precondition.

### 2.5 Catalog-number sparsity within label

For the 222 multi-record labels with ≥ 3 owned records and an extractable numeric component:

| Density bucket (= records / (max_num − min_num + 1)) | # labels | % |
|---|---:|---:|
| Dense (≥ 0.5) — most contiguous numbers owned | 29 | 13.1% |
| Medium (0.1–0.5) | 66 | 29.7% |
| **Sparse (< 0.1)** — large gaps in catalog-# space relative to # owned | **127** | **57.2%** |

Median gap (median across labels) between consecutive owned catalog numbers: **12**.
- Labels with median gap = 1 (perfectly contiguous run): 20
- Labels with median gap > 10 (sparse): 114
- Labels with max gap > 100 (big holes in numbering): 111

**Key implication for algorithm choice:** the user's collection is **dominated by sparse, gappy multi-record labels**. The naïve "linear interpolation by catalog-number value" candidate (§4.2) will be inaccurate on these — it implicitly assumes density. Approaches that interpolate over the user's *owned* index (§4.1, §4.3, §4.5) handle sparsity correctly by construction. This is the main empirical lever.

### 2.6 Anomalies worth knowing

- One large label has a `numeric_range` of **5 × 10¹²** — almost certainly because at least one catalog number is a barcode-style 13-digit ID. The "longest digit run" heuristic explodes on this; any numeric-aware comparator must either (a) cap digit-run consideration, (b) detect barcodes by length and demote them, or (c) treat the digit run as a sequence-of-digits-of-bounded-length and fall back to lexicographic on overflow.
- 3 records have *no digits at all* in their catalog#. Any numeric-aware comparator must define a deterministic order for these (suggested: treat the numeric component as `-∞` so they sort first, or a sentinel like `None` with stable lexicographic fallback).

---

## 3. Catalog-Number Parsing — Approach Taxonomy

This is an **orthogonal sub-problem**. Every interpolation algorithm in §4 depends on a *comparator* and (for value-based methods) a *numeric coordinate extractor*. The parser is the layer that produces both. Per `PITFALLS.md` Pitfall 1, this is the position estimator's responsibility, not the database's; `cube_boundaries` stores display catalog numbers verbatim and the estimator normalizes both endpoints + query at compute time.

### 3.1 Parsing strategies

#### A. Pure numeric extraction (regex)
Lift the longest (or first) digit run, parse to int.

```python
def numeric_key(cat: str) -> int:
    m = max(re.findall(r"\d+", cat), key=len, default="0")
    return int(m)
```

**Pros:** trivial, fast (microseconds), zero dependencies.
**Cons:** ignores prefix entirely (`BLP 4195` and `BST 4195` look identical). Breaks the multi-prefix case (34.8% of multi-record labels). Cannot order pure-alpha records. Vulnerable to the 13-digit barcode outlier in §2.6.

#### B. Structured `(prefix, number, suffix)` split
Split on the alpha→digit boundary; keep all three parts. Compare as a tuple.

```python
PATTERN = re.compile(r"^(?P<prefix>[A-Za-z]*)(?P<digits>\d*)(?P<suffix>.*)$")
def structured_key(cat: str) -> tuple[str, int, str]:
    m = PATTERN.match(cat.strip())
    p, d, s = m.group("prefix"), m.group("digits"), m.group("suffix")
    return (p.upper(), int(d) if d else -1, s)
```

**Pros:** keeps prefix as a sort key (handles multi-prefix within label). Numeric run compared numerically. Cheap.
**Cons:** assumes a single prefix/digits/suffix shape. The 6.7% "alpha-digits-alpha" and 2.2% "digits-alpha-digits" structured-but-different shapes need extra cases or a more general tokenizer.

#### C. Token-stream split (recommended general form)
Generalize B: alternate runs of `[A-Za-z]+` and `\d+`, plus an optional trailing separator key. Each token compared by type-then-value.

```python
TOKEN = re.compile(r"([A-Za-z]+|\d+)")
def token_key(cat: str) -> tuple:
    out = []
    for tok in TOKEN.findall(cat):
        if tok.isdigit():
            out.append((1, int(tok)))    # type-tag 1 = numeric; sorts after alpha for the same position
        else:
            out.append((0, tok.upper())) # type-tag 0 = alpha (case-folded)
    return tuple(out)
```

**Pros:** handles every shape in §2.3, including `9NUM005`, `BLP 4195`, `2SHOT-099`, pure numerics, pure alphas. Comparator is total. Stable under separator differences (separators are not tokens).
**Cons:** ~5 µs per call (still negligible; 32 boundaries × ~5 µs = 160 µs, well within budget). Two records that differ *only* in separator collapse to equal keys — usually correct but loses an information bit. Slight risk of false equality on rare cases like `BLP 4195` vs `BLP4195` — these would sort equal under this scheme; that may be the *desired* behavior, but tag it as a deliberate decision.

#### D. Library-based: `natsort`
Use `natsort.natsort_keygen(alg=ns.IGNORECASE | ns.SIGNED | ns.LOCALE)` and reuse the resulting key function.

**Pros:** battle-tested. Handles edge cases (signed numbers, locale-aware case folding, Unicode digits) we don't have to implement. Latest is 8.4.x; pure Python with optional `fastnumbers` extra for ~2× speedup. ~3 KB of additional dependencies via `fastnumbers`.
**Cons:** opaque about its decisions (some users want explicit control of separator handling). The behavior on multi-value catalogs is whatever `natsort` does to the comma — usually safe, but worth pinning with a property test. Adds a third-party dependency that the project otherwise wouldn't need.

#### E. Custom layered normalizer (per `PITFALLS.md` recommendation)
The pipeline described in Pitfall 1: case-fold → collapse separator runs to a canonical separator → split into `(alpha_prefix, numeric_suffix, trailing)` → compare numerically on the digit run, lexicographically on the rest.

**Pros:** explicit, every step is testable. Matches the architecture document. Same code path used by the boundary save validator (Pitfall 1 prevention bullet).
**Cons:** more code to maintain than calling `natsort`. The "split into prefix + digits + trailing" shape is essentially strategy B with normalization; for the 6.7% and 2.2% multi-segment shapes you still need to recurse or extend (i.e., it converges toward strategy C in practice).

### 3.2 Pre-comparison normalization (applies to all strategies)

Regardless of which strategy above is chosen, the following preprocess steps should be applied uniformly to both stored boundary endpoints and the queried record's catalog#:

1. **Trim whitespace** (`strip()`).
2. **Unicode normalize** (`unicodedata.normalize("NFKC", s)`) — collapses full-width digits, ligatures, and any oddities a Discogs editor copied in from a PDF.
3. **Case fold** (`str.casefold()` not `lower()` — handles `ß` → `ss` and locale-folded chars; matches the user's mental model that case is insignificant).
4. **Collapse separators** (`re.sub(r"[\s\-_./]+", " ", s)` or omit-separator entirely depending on whether `BLP4195` and `BLP 4195` should compare equal — recommend collapse-to-single-space; treat separator presence as significant only for *display*, not for *ordering*).
5. **Multi-value handling** — if comma is present, **keep only the first part** for sort/compare purposes. Store the full multi-value string verbatim for display.
6. **Empty / placeholder handling** — `none`, `n/a`, blank: replace with a `NONE_SENTINEL` token that sorts deterministically (e.g., first or last per a documented choice).

### 3.3 Comparator vs coordinate function

The estimator needs *two* things from the parser:

1. **A total-order comparator** — used for `first ≤ query ≤ last` interval checks and for the boundary save validator. Strategies B, C, D, E all provide this; A provides only a partial order.
2. **A 1-D coordinate function** (for value-based interpolation, §4.2) — maps a catalog# inside a label to a real number. This is **separate from the comparator** and exists only for labels where it's well-defined: a single dominant prefix, monotone digit runs. For multi-prefix or non-numeric labels, the coordinate function returns `None` and the estimator must fall back to an index-based candidate. Detect this at parse time and propagate a "coordinate-available" flag.

### 3.4 Test invariants for the parser layer

These are invariants the parser code should *prove* via Hypothesis tests; they are independent of which interpolation algorithm wins:

- **Total order:** for any two parsed keys, exactly one of `a < b`, `a == b`, `a > b` holds.
- **Idempotent under double-normalize:** `parse(parse_display(x)) == parse(x)`.
- **Stable under cosmetic transforms:** `parse("BLP 4195") == parse("blp-4195") == parse("BLP\t4195")`.
- **Numeric-aware on digit run:** `parse("BLP 9") < parse("BLP 10")` (this is the test that ASCII sort fails).
- **Multi-prefix discriminates:** for labels where `parse_label` would give `BLP 4001` and `BST 4001`, `parse("BLP 4001") != parse("BST 4001")` and they sort in a deterministic order.
- **Round-trip with the seed CSV's hand-curated golden list** (per `PITFALLS.md` Pitfall 1 prevention bullet): for each label, sorting its catalog#s under `parse_key` matches the hand-curated list.

---

## 4. Algorithm Candidates

Each section follows a uniform schema: **inputs**, **algorithm sketch**, **complexity**, **strengths**, **failure modes**, **maintenance**, **fit to the real collection**, **implementation effort**.

### Summary comparison table

| # | Approach | Inputs beyond `cube_boundaries` | Time | Complexity (S/M/L) | Accuracy on dense+uniform | Accuracy on sparse+gappy | Multi-prefix-safe? | Re-fit on collection change? |
|---|---|---|---:|---:|---:|---:|:---:|:---:|
| 1 | Linear by index | label's owned records | O(log N + log k) | S | Excellent | Excellent | If parser is | No |
| 2 | Linear by catalog-# value | nothing | O(log N) | S | Excellent (when dense) | **Poor** | No (prefix info lost) | No |
| 3 | Empirical CDF (per-label) | label's owned records | O(log N + log k) | M | Excellent | Excellent | Yes (with parser) | No (recomputed per call cheap) |
| 4 | Piecewise-linear, cube-anchored | boundary catalog#s + label's owned records | O(log N + log k) | M | Excellent | Good | If parser is | No |
| 5 | k-nearest-neighbor | label's owned records | O(log N + log k) | M | Good (k=1 → equiv to index) | Good | Yes | No |
| 6 | Hybrid: index for span, value within cube | label's owned records + boundary catalog#s | O(log N + log k) | M | Excellent | Good | If parser is | No |
| 7 | Lookup-table refresh | offline build of full record→position map | O(1) | L | Perfect (it's a snapshot) | Perfect | Yes (parser used offline) | **Yes, every change** |
| 8 | No interpolation (cube only) | nothing | O(log N) | S | N/A (interval = full cube) | N/A | Yes | No |
| 9 | Isotonic regression / monotone calibration | label's owned records | O(k log k) per label | M-L | Excellent | Excellent | Yes | Recompute per-label cache on change |
| 10 | Density-aware (gap-weighted index) | label's owned records | O(log N + log k) | M | Excellent | **Best on the real shape** | Yes | No |

*N = total records (~3,030). k = records-in-label (median 1, max 51).*

A note on "time": every candidate is bounded by O(log N) for finding the label's record window and O(log k) for finding the target within it. All candidates fit in the 50 ms budget by an order of magnitude or more — the differentiator is **accuracy on the user's actual distribution shape**, not speed.

---

### 4.1 Linear interpolation by index

**Sketch.** Among the user's owned records, find the contiguous run of records belonging to the queried label, sorted by parsed catalog key. Locate the queried record's index `i` within that run of length `k`. Position fraction `f = i / max(k − 1, 1)`. Map `f` across the label's `label_span` cubes (almost always one cube) to get the sub-cube interval.

```python
def position_by_index(label_records, target_id):
    sorted_recs = sorted(label_records, key=lambda r: parse_key(r.catalog))
    idx = next(i for i, r in enumerate(sorted_recs) if r.id == target_id)
    f = idx / max(len(sorted_recs) - 1, 1)
    return f
```

**Inputs:** the label's owned records (a slice of `v_collection` filtered to `label = X`). One DB-free lookup if the entire collection is held as an in-memory dict-by-label, which is plausible at 3,030 rows (~ a few hundred KB). Otherwise one indexed query at boot.

**Strengths:** Deterministic by construction. Naturally handles sparsity, gaps, and multi-prefix labels (the parser orders them, the index ignores numerical scale). Robust to one outlier catalog# (Label_10's barcode-style entry from §2.6 doesn't pull the interpolation off — it's just one more slot in the ordered list).

**Failure modes:** Assumes the user owns a representative spread within the label's shelf range. If the user owns 5 of a label's 50 releases and those 5 happen to cluster at one end of the label's catalog space, "index 3 out of 5" maps to 60% of the *owned* range but says nothing about the 60% mark of the *physical* range. In practice, since the user's shelf is sorted by what they *own* (not by what exists in the universe), this is the *correct* behavior — index *is* shelf position.

**Multi-prefix safety:** Inherits from the parser. If `parse_key` correctly orders `BLP 4001 < BST 1234 < BST 4001`, the index-based interpolation places them correctly.

**Maintenance:** Zero. No re-fitting. The owned-record list updates automatically with each discogsography sync; the next `/api/locate` reads the new state.

**Fit to the real collection:**
- Singletons (26.6% of records): `k = 1` ⇒ `f = 0` by the formula. Document this as the singleton convention; the sub-cube interval defaults to the cube's full width with `confidence = "singleton"`.
- Sparse labels (57.2% of the multi-record labels): exactly what index-based interpolation handles best.
- 35.6% raw-vs-natural sort divergence: handled by the parser, transparent to this algorithm.

**Implementation effort:** **S**. About 30 lines of Python.

---

### 4.2 Linear interpolation by catalog-number value

**Sketch.** Extract a 1-D numeric coordinate from each catalog# (per §3.3). Within the label, the queried record's coordinate is `c`, the minimum and maximum are `c_min` and `c_max`. Position fraction `f = (c − c_min) / (c_max − c_min)`.

```python
def position_by_value(label_records, target_record):
    coords = [coord(r.catalog) for r in label_records]
    c = coord(target_record.catalog)
    return (c - min(coords)) / (max(coords) - min(coords))
```

**Inputs:** Same as index, but needs the coordinate function to be defined for every record in the label.

**Strengths:** Faithful to "real" position when catalog numbers are dense and monotone — e.g., a label where the user owns `XYZ 100`, `XYZ 105`, `XYZ 110`, `XYZ 120`: the value-based interpolation puts `XYZ 110` at 50% (correct relative to the catalog space), while index-based puts it at 67%. The "right answer" depends on how the *physical shelf* is arranged. If the user hand-sorted by catalog number, both approaches agree on order but differ on spacing.

**Failure modes (severe on this collection):**
- Sparse labels (57% of multi-record labels): the coordinate function "stretches" the few owned records across the full numeric range, *misrepresenting* the shelf which only contains the owned records. A record with `c = c_min + 5%` of the range and `c = c_min + 95%` of the range may be *adjacent* on the shelf.
- Multi-prefix labels (34.8%): no single coordinate function works — `BLP 4195` and `BST 84001` need to share a number line. Choices are: ignore prefix (wrong: collapses them), inject prefix as a large constant offset (arbitrary), or refuse to use this method on multi-prefix labels (best — fall back to §4.1).
- Pure-alpha catalogs (3 records in this collection): no coordinate. Fall back to §4.1.
- The 13-digit barcode outlier from §2.6 makes `c_max − c_min` astronomically large; every "normal" record collapses to `f ≈ 0`.

**Multi-prefix safety:** **No**, by default. Requires a guardrail that detects multi-prefix and falls back.

**Maintenance:** Zero re-fit. But the "is this label value-interpolatable?" flag has to be recomputed when collection state changes — trivially cheap (one pass per label).

**Fit to the real collection:** **Poor as a sole strategy**, useful as a *refinement* on labels that pass a density check. Only ~13% of multi-record labels (~ 5–6% of records via the labels' record counts) are dense enough to materially benefit. Recommended for the §4.6 hybrid, not as a primary.

**Implementation effort:** **S**. ~25 lines. Most of the work is in the guardrails (density check, multi-prefix detector, outlier detector).

---

### 4.3 Empirical CDF using collection density

**Sketch.** Build the CDF of catalog-number coordinates *over the user's owned records in the label*. For the target with coordinate `c`, position fraction `f = CDF(c) = (number of owned records with coord ≤ c) / total owned`. This is mathematically equivalent to index-based interpolation when the CDF is a step function over exactly the owned records — i.e., **§4.3 ≡ §4.1 in the case where the CDF is empirical-only**. The candidates diverge when the CDF is smoothed (kernel density) or when it incorporates side information (e.g., known-but-unowned catalog numbers from a Discogs *label discography* query).

**Inputs:** label's owned records, optionally an external "all releases for this label" list (which would require a discogsography query and explicitly was rejected for v1).

**Strengths:** The smoothed variant captures continuous density without committing to either pure-index or pure-value semantics. Robust to the multi-prefix case if each prefix is its own "bin" in a stratified CDF.

**Failure modes:** Pure empirical CDF is just §4.1 in different notation. Smoothed CDF requires choosing a bandwidth and a kernel — adds knobs without obvious benefit at small `k`. If `k = 1`, the CDF is a step function with one step; same singleton problem as everything else. With sparse labels (typical) and `k < 5`, KDE smoothing is statistically meaningless.

**Multi-prefix safety:** With stratification (one CDF per prefix), yes. Adds significant complexity for marginal benefit.

**Maintenance:** Empirical version is zero-fit. Smoothed version's bandwidth could in principle be tuned per-label, which is L-complexity busywork.

**Fit to the real collection:** As a *concept*, recasts §4.1 in CDF language without behavior change. The smoothed variant is not justified by the data: at median `k = 1` and 405 multi-record labels, statistical smoothing buys nothing.

**Implementation effort:** **S** (empirical), **M** (smoothed). Recommend treating §4.3 as a *re-statement* of §4.1 in this project and not implementing it as a separate path.

---

### 4.4 Piecewise-linear, cube-anchored interpolation

**Sketch.** When a label spans multiple cubes (rare per §2.2; expected ~10% of records), the two cube boundaries that fall *within* the label give us two anchor points: the catalog# at which cube N ends and cube N+1 begins. Within each cube, fit a linear function `position(catalog) = a × catalog + b` using the boundary records on the cube's edges and the label's own min/max as endpoints. Within a single-cube label, this degenerates to §4.2 (linear by value) with `c_min` and `c_max` taken from boundary endpoints rather than label endpoints — which is **subtly different**: the cube boundaries reflect the user's hand-arrangement, not the label's true min/max.

**Inputs:** `cube_boundaries` + label's owned records + the coordinate function.

**Strengths:** When the label spans two cubes, the boundary record itself is a *ground-truth anchor* — the user literally placed it on the cube edge. Interpolating relative to this anchor is more accurate than label-wide value-interpolation for that 10% of records.

**Failure modes:** Inherits §4.2's value-interpolation fragility within each cube segment. Specifically: if the cube boundary itself is a record from a *different* label (which it usually will be, given §2.2 — labels don't span boundaries on purpose), the anchor doesn't apply to *this* label. Boundary semantics from `ARCHITECTURE.md` state cube boundaries are `(label, catalog#)` pairs — an anchor from another label gives no information about how this label is arranged.

The genuine cube-anchor case is only when *both* the cube-ending and cube-starting boundary records share the queried label, meaning the label legitimately straddles that boundary. By §2.2 this affects ~10% of records and provides actually useful anchor information.

**Multi-prefix safety:** Inherits from the parser and the coordinate function. Anchored interpolation provides genuine info only if the anchor records are in the same prefix family as the query.

**Maintenance:** Recompute the per-label anchor map when boundaries change. The boundary cache invalidation already covers this for free.

**Fit to the real collection:** Useful for the ~10% of records whose label spans 2 cubes. Diminishes to §4.2 elsewhere (which we've argued is the wrong default).

**Implementation effort:** **M**. Anchor-detection logic is fiddly: "which boundary record applies to this label's interpolation?" is a careful predicate.

---

### 4.5 k-nearest-neighbor on owned records

**Sketch.** Find the `k` records in the queried label whose parsed catalog keys are closest to the query's key. For each neighbor, compute its known shelf position (assumed known via §4.1 applied to the neighbor itself). Average. Optionally weight by 1/distance.

```python
def position_by_knn(label_records, target, k=3):
    neighbors = nsmallest(k, label_records, key=lambda r: abs(coord(r.catalog) - coord(target.catalog)))
    return sum(position_of(n) for n in neighbors) / len(neighbors)
```

**Inputs:** label's owned records + coordinate function (or a key-distance function).

**Strengths:** Robust to one outlier (the neighbor average smooths over it). For `k = 1` and a target equal to an existing record, returns that record's position exactly.

**Failure modes:** Needs a meaningful distance function on the parsed keys. Token-stream keys (strategy C in §3.1) are tuples — defining "distance between tuples" is awkward. Falls back to coordinate-based distance, which inherits §4.2's problems on sparse/multi-prefix labels. With median `k_label = 1`, "3 nearest neighbors" is meaningless — there *are* no 3 records.

**Multi-prefix safety:** Only if distance respects prefix. A naïve numeric distance puts `BLP 4001` close to `BST 4001` (distance = 0 in the digit run), which is wrong.

**Maintenance:** Zero.

**Fit to the real collection:** With 805 singleton labels (26.6% of records) and another 27% of records in labels of size 2–3 (where `k = 3` exhausts the label), the value of "averaging neighbors" is unclear. KNN is a tool for data-rich settings; this isn't one.

**Implementation effort:** **M**. The distance function is the trap.

---

### 4.6 Hybrid: index for label-span coarse, value within cube fine

**Sketch.** Two-pass interpolation.
1. **Coarse pass (which cube):** apply §4.1 (index) to determine which cube the record falls into within the label-span.
2. **Fine pass (sub-cube position):** *within* the chosen cube, apply §4.2 (value) using the cube's first/last catalog# as anchors and the queried record's catalog# as the value.

```python
def position_hybrid(label_records, boundaries, target):
    f_index = position_by_index(label_records, target)
    cube = pick_cube(label_records, f_index, boundaries)
    f_value = (coord(target.catalog) - coord(cube.first_catalog)) / (coord(cube.last_catalog) - coord(cube.first_catalog))
    return (cube, f_value)
```

**Inputs:** label's owned records + `cube_boundaries` + coordinate function.

**Strengths:** Uses the user's hand-sorted order at the cube level (the right answer) and the catalog-space at the within-cube level (where it tends to be locally dense even for sparse labels overall). Robust to sparsity at the label scale because the within-cube range is narrow.

**Failure modes:** The within-cube `c_min`, `c_max` are the cube's boundary records, which are *some other label* in ~90% of cases. The value function on `cube.first_catalog` (say it's from label X with prefix `XYZ`) and the target (label Y with prefix `ABC`) is **not comparable**. The fine pass essentially defaults to `f_value = 0.5` in those cases — the same as no fine pass at all.

The fine pass is genuinely useful only when boundary records share the queried label (the ~10% spanning case from §2.2). Outside of that, the algorithm degrades to §4.1 with a degenerate fine pass.

**Multi-prefix safety:** Inherits both from parser and from the same-label-anchor caveat.

**Maintenance:** Same as §4.4 + §4.1.

**Fit to the real collection:** Good when the label spans a cube boundary; otherwise no better than §4.1.

**Implementation effort:** **M**. Three parts: index pass, anchor-eligibility check, value pass.

---

### 4.7 Lookup-table refresh (precomputed)

**Sketch.** Periodically (e.g., after each discogsography sync, after each boundary edit), iterate every record in the collection, compute its `(primary_cube, label_span, sub_cube_interval, confidence)` using any of the algorithms above, and write the result into a `release_positions` table keyed by `release_id`. At query time, single O(1) lookup.

**Inputs:** Full collection + boundaries; rebuild trigger.

**Strengths:** Query time becomes a DB index lookup — well under the 50 ms budget by orders of magnitude. Inspection-friendly: an admin can see *every* record's stored position at once for audits.

**Failure modes:**
- Stale results between refreshes. After a boundary edit, the table is wrong until refreshed. Refresh triggers need to be airtight (Postgres trigger? Application-level invalidation? Both?).
- The refresh has to *use* an algorithm — this is not a replacement for §4.1–4.6, it's a cache *on top* of one. Algorithm bugs become *persisted* algorithm bugs.
- 3,030 rows × 32 cubes × table writes ≈ trivial in absolute terms, but adds operational moving parts that the architecture explicitly minimizes ("Position … is computed, not stored per-record" — `PROJECT.md` Key Decisions).
- `ARCHITECTURE.md` §Anti-Pattern 2 explicitly calls this out as a thing to *avoid* per `PROJECT.md`'s key decisions.

**Multi-prefix safety:** Whatever the offline algorithm does.

**Maintenance:** **High.** Refresh on every boundary edit *and* every collection sync. Race conditions if both happen near each other. Versioning column needed so the kiosk can detect "this row is from an old algorithm version, recompute."

**Fit to the real collection:** Useful if and only if computed-on-demand becomes a measured bottleneck. At 32 boundaries + 3,030 records and median `k = 1`, on-demand will be sub-millisecond. **Recommend against** unless profiling forces it.

**Implementation effort:** **L**. Refresh logic, triggers, version pinning, race-condition handling.

---

### 4.8 No interpolation — return cube only (strawman / floor)

**Sketch.** Find the cube(s) the label sits in via boundary lookup. Return `sub_cube_interval = None` (or the cube's full width). User scans the cube visually.

**Inputs:** `cube_boundaries`.

**Strengths:** Truly trivial. Defines the lower bound on what "doing nothing" achieves. **Required as a comparison baseline** for the test harness — every other algorithm's claimed accuracy improvement is measured against this floor.

**Failure modes:** A cube holds ~95 records on average; "anywhere in this cube" is not much help for a record at index 70 of 95.

**Maintenance:** None.

**Fit to the real collection:** Acceptable for singletons (26.6% of records): the cube *is* the answer. Worse than acceptable for medium-density labels.

**Implementation effort:** **S**. ~5 lines. Already covered by the contract's "estimator timeout" fallback path.

---

### 4.9 Isotonic regression / monotone calibration

**Sketch.** For each multi-record label, fit a monotone non-decreasing function `position(catalog_coord) = isotonic_regression(records)` once at boot (or on collection change). Query: evaluate the fitted function at the target's coordinate. This is the formal-statistics version of "interpolate but respect order".

**Inputs:** label's owned records + coordinate function. Fitted curve persisted in an in-memory per-label cache.

**Strengths:** Mathematically clean. Handles arbitrary monotone-but-non-linear catalog-#-to-position relationships. Implementable in ~one call: `sklearn.isotonic.IsotonicRegression().fit(coords, positions)`. The fitted function is just a step function over the data, so evaluation is `O(log k)`. *In the median case (k = 1) it degenerates to a constant.*

**Failure modes:** For `k ≤ 3` (most multi-record labels), isotonic regression is a step function — identical to §4.1's index-based result. Heavier statistical machinery for the same answer. Sklearn dependency (~30 MB transitive) just for `IsotonicRegression` is a lot of weight; could use `scipy.stats.isotonic_regression` directly (8 KB function in scipy).

**Multi-prefix safety:** Only with stratification per prefix. Same caveat as everywhere.

**Maintenance:** Refit per-label on collection change. With 405 multi-record labels and trivial regression sizes, the refit takes < 50 ms total — cheap. Triggered by the same bus event as boundary cache invalidation.

**Fit to the real collection:** Theoretically clean, practically equivalent to §4.1 for nearly every label in this collection because k is too small for the curve-fitting flexibility to matter. **Use only if** the test harness shows §4.1 has accuracy issues that isotonic would fix — unlikely given the data shape.

**Implementation effort:** **M-L**. The estimator itself is short; the dependency, the refit lifecycle, and the cache invalidation add up.

---

### 4.10 Density-aware (gap-weighted) index interpolation

**Sketch.** A refinement of §4.1 specifically designed for the sparse-label case (57% of multi-record labels). Within a label, compute a *cumulative weight* over the sorted record list where each record contributes a weight equal to its catalog-# gap to the next record (capped at some maximum). The query position is the cumulative weight up to and including the target, divided by total weight. This is mathematically a weighted CDF; the weight reflects "how much shelf space this record occupies".

```python
def position_density_weighted(label_records, target):
    sorted_recs = sorted(label_records, key=lambda r: parse_key(r.catalog))
    coords = [coord(r.catalog) for r in sorted_recs]
    # gap to next record (cap large gaps to avoid the barcode outlier)
    gaps = [min(coords[i+1] - coords[i], CAP) for i in range(len(coords) - 1)] + [1]  # final record gets unit weight
    cumweight = list(itertools.accumulate(gaps))
    total = cumweight[-1]
    idx = next(i for i, r in enumerate(sorted_recs) if r.id == target.id)
    return cumweight[idx] / total
```

**Inputs:** label's owned records + coordinate function (where available; fallback to uniform weight otherwise).

**Strengths:** Captures the intuition that "if there's a big numeric gap between two adjacent owned records, the shelf likely has them more spaced apart" (the user may have left physical space, or the gap reflects unowned releases that other records lean into). Caps make it robust to outliers like the 13-digit barcode. Degenerates to §4.1 when gaps are uniform.

**Failure modes:** The "shelf reflects catalog-space gaps" assumption is a hypothesis, not a fact. The user may pack records tightly regardless of catalog gaps. **This is the canonical case where the algorithm choice is empirical.**

**Multi-prefix safety:** With stratification per prefix; treat each prefix family as a separate run within the label. Total weight = sum across families.

**Maintenance:** Zero — cumulative weight recomputed per call from the owned records (cheap at k ≤ 51).

**Fit to the real collection:** Targets exactly the dominant data shape — sparse multi-record labels. The test harness should compare §4.1 (pure index) vs §4.10 (density-weighted) on every multi-record label and report which has lower mean absolute error against the user's hand-curated golden cases.

**Implementation effort:** **M**. ~50 lines. The cap is a parameter to tune.

---

## 5. Combining Approaches (Hybrid Strategies)

The candidates above are not mutually exclusive. Two specific combinations are worth surfacing:

### 5.1 Tiered cascade by label shape

A single dispatch function picks the algorithm per query based on the queried label's shape:

```python
def estimate(target):
    recs = label_records(target.label)
    if len(recs) == 1:                         # 26.6% of records
        return SINGLETON_FALLBACK
    if multi_prefix_detected(recs):            # ~34.8% of multi-record labels
        return position_by_index(recs, target) # §4.1
    if numeric_range_or_outlier_too_large(recs):
        return position_by_index(recs, target) # §4.1
    if density(recs) >= DENSE_THRESHOLD:       # ~13% of multi-record labels
        return position_hybrid(recs, target)   # §4.6
    return position_density_weighted(recs, target)  # §4.10 — the rest
```

This trades complexity for accuracy on each subset. **Confidence is reported per-tier** (e.g., singleton = 0.3 because span = full cube; dense = 0.8; sparse + density-weighted = 0.6; multi-prefix = 0.55). The contract permits this; downstream UI uses confidence to attenuate the position-bar overlay's intensity.

### 5.2 Algorithm + monotone safety net

Pick any single algorithm from §4 as primary. After computing the result, run an isotonic-regression sanity check against the label's owned records: if the algorithm output is non-monotonic in the catalog ordering (i.e., record A's predicted position exceeds record B's even though A's catalog key is smaller), the result is *known to be wrong*. The estimator returns the algorithm's answer but downgrades confidence to 0.2 and logs a diagnostic.

This is a cheap correctness gate (one `O(k log k)` check per label) that catches algorithmic regressions without committing to isotonic as the primary method.

### 5.3 Two-pass with confidence feedback

If the primary algorithm returns `confidence < 0.5` (e.g., singleton, multi-prefix collision, or density-weighting on `k = 2`), the estimator can *also* run the strawman §4.8 and return a wider sub-cube interval — essentially "I'm not sure, look at the whole cube". The two pieces of information (point estimate + falled-back interval) can both be returned, with the UI rendering either as a thin precise band or a wide gradient based on confidence.

---

## 6. Edge Cases & Their Handling

| Edge case | Frequency | Handling |
|---|---|---|
| Singleton label (`k = 1`) | 26.6% of records | Position fraction defined as 0.5 by convention; sub_cube_interval = full cube width. Confidence tagged `"singleton"`. |
| Pure-alpha catalog# (no digits) | 3 records (0.1%) | Sort key sentinel (e.g., numeric component = `-1`). Coordinate function returns `None`; value-based algorithms fall back to index. |
| Placeholder catalog# (`none`, `n/a`) | 47 records (1.6%) | Same as pure-alpha: sentinel value; sort with a documented placement (recommend: sort first within label so they're predictable). |
| Multi-value catalog# (commas) | 394 records (13.0%) | Strip to first value for sort/compare; preserve full string for display. Document this in the comparator's docstring and pin with a property test. |
| Multi-label record (`Label` field has commas) | 573 records (18.9%) | Use the raw `Label` string as the sort key — matches the user's CSV-driven mental model. Splitting it would re-shelf the record. |
| Multi-prefix within label | 141 multi-record labels (34.8%) | Parser keeps prefix as part of the sort key; tiered cascade routes these to index-based interpolation (§4.1) since value-based methods can't bridge prefixes meaningfully. |
| Mixed separators within label | 168 multi-record labels (41.5%) | Parser collapses separators in the sort key; display preserves them verbatim. The 35.6% sort-mismatch number is the binding constraint that drives this. |
| Mixed case within label | 86 multi-record labels (21.2%) | Case-folded in the sort key; preserved in display. |
| Varying digit lengths within label | 142 multi-record labels (35.1%) | Numeric-aware comparator (compare digit runs as integers, not as left-padded strings). Pure-ASCII sort fails here; this is the most visible Pitfall 1 manifestation. |
| Barcode-style 13-digit catalog# | ≥ 1 known label | Coordinate function caps digit-run length (e.g., > 8 digits triggers fall-back to index ordering, value coordinate = `None`). Or: treat barcode-shaped as a separate prefix family. |
| Record's label has no boundary covering it | unknown frequency | Per contract: HTTP 200 with `confidence: 0.0`, `primary_cube: null`, `label_span: []`. UI renders "no cube assigned yet". This is the admin's signal to run the wizard. |
| Label legitimately spans two cubes | ~10% of records (estimated) | Primary algorithm computes position fraction across the label; the cube selection follows from that fraction. `sub_cube_interval` reports `crosses_boundary = true` only if the *uncertainty interval* spans the boundary (which is mostly a confidence question). |
| Boundary points at a phantom record | depends on sync state (Pitfall 2) | Estimator does interval lookup, not exact match — survives. The wizard's "auto-suggest midpoint" is the consumer that breaks; that's a separate algorithm (suggest endpoint walks `v_collection`, not catalog space, per `PITFALLS.md` Pitfall 22 prevention). |

---

## 7. Validation Methodology

The estimator is the highest-leverage research stream in v1 — the algorithm choice influences directly observable kiosk behavior on every search. The validation strategy mirrors `STACK.md` §"Testing the Position-Estimation Algorithm" and the Hypothesis property recommended in `PITFALLS.md` Pitfall 1.

### 7.1 Test harness composition

| Layer | Purpose | Tools |
|---|---|---|
| **Parser unit tests** | Pin the comparator on the 8 case categories from §3.4 | `pytest` |
| **Parser property tests** | Total-order, idempotence, cosmetic-invariance | `Hypothesis` |
| **Parser golden tests** | Per-label sort order matches a hand-curated list from the CSV | `pytest` parametrize over a fixture file |
| **Algorithm unit tests** | Each `position_by_*` function returns valid `[0,1]` on canned inputs | `pytest` |
| **Algorithm property tests** | Monotonicity (queried position is monotone in catalog key); span containment (`primary_cube ∈ label_span`); stability under separator/case noise | `Hypothesis` |
| **Algorithm benchmark** | p95 ≤ 50 ms over a realistic distribution of queries | `pytest-benchmark` |
| **Boundary save validator** | Re-uses the parser's comparator; `first ≤ last` rejection test | `pytest` |
| **Reverse-direction sanity** | For every record, simulate the user "walking to the cube and looking left-to-right"; the predicted position should match the hand-curated expectation | manual review of a 30-record sample |

### 7.2 Required golden case set (minimum)

Build a `golden_cases.yaml` fixture with at least one example per row of the distribution-shape taxonomy below. Pin both the chosen algorithm's output and the *human-judged-correct* answer. When the two diverge, that's a research finding.

| Case category | Example shape (synthetic — no PII) | Records needed |
|---|---|---:|
| Singleton | Label with 1 record | 1 |
| Tight pair | Label with 2 records, adjacent catalog#s | 1 |
| Small dense label | 4–5 records, contiguous range | 1 |
| Sparse multi-record | 5 records, max gap > 100 | 1 |
| Multi-prefix | 6 records, 3 each from 2 prefixes (`BLP`/`BST` shape) | 1 |
| Mixed separators | 4 records, both `XX 001` and `XX-002` style | 1 |
| Mixed case | 3 records, `Wraith 998`/`WRAITH 999` shape | 1 |
| Varying digit lengths | 4 records with `9`/`10`/`100`/`1000` digit runs | 1 |
| Barcode outlier | 5 records, one a 13-digit catalog | 1 |
| Pure-alpha catalog | 1 record with no digits | 1 |
| Placeholder catalog | 1 record with `none` | 1 |
| Two-cube span | 30+ records, hand-confirmed to cross a cube boundary | 1 |
| Multi-value catalog# | 2 records with commas | 1 |

Total: ~13 golden cases. Each one's "expected output" is reviewed by the owner; algorithm changes that flip any expected output are flagged for re-review.

### 7.3 Hypothesis properties (algorithm-agnostic invariants)

```python
@given(release_id=st.sampled_from(all_release_ids))
def test_locate_returns_valid_position(release_id):
    r = estimator.locate(release_id)
    assert r.primary_cube in r.label_span
    if r.sub_cube_interval is not None:
        assert 0.0 <= r.sub_cube_interval.start <= 1.0
        assert r.sub_cube_interval.start <= r.sub_cube_interval.end

@given(label=st.sampled_from(multi_record_labels))
def test_monotone_within_label(label):
    recs = sorted(records_of(label), key=lambda r: parse_key(r.catalog))
    positions = [estimator.locate(r.id).flatten_position() for r in recs]
    assert positions == sorted(positions)

@given(release_id=st.sampled_from(all_release_ids),
       perturbation=cosmetic_perturbations)  # whitespace / case / separator noise
def test_stable_under_cosmetic_noise(release_id, perturbation):
    r1 = estimator.locate_with_catalog(release_id, original_catalog)
    r2 = estimator.locate_with_catalog(release_id, perturbation(original_catalog))
    assert r1.primary_cube == r2.primary_cube
    assert (r1.sub_cube_interval is None) == (r2.sub_cube_interval is None)
```

### 7.4 A/B test harness for algorithm comparison

Build a `run_all_algorithms.py` developer script that, given the CSV and a hand-set `cube_boundaries` fixture (the owner's actual reshuffle once they've done it), runs candidates §4.1–§4.10 against the full collection and reports per-label and aggregate:

- Mean absolute error between algorithm position and a "ground truth" position (computed as the record's actual rank within the label, normalized).
- Per distribution-shape bucket (singleton, sparse, dense, multi-prefix, etc.).
- Time per call (validate the 50 ms budget).
- Confidence distribution.

This script is *the* tool for picking the algorithm. Without it, all comparison is speculation.

### 7.5 Performance budget proof

A `pytest-benchmark` test that asserts p95 < 50 ms for `estimator.locate()` over a sample of 1,000 random queries against the boundary cache + in-memory collection snapshot. CI-gated. If the cache strategy changes, this test catches regressions.

### 7.6 CI vs local validation

Per `STACK.md` §Testing, the real CSV is gitignored. CI runs against:
- A small synthetic dataset (50 labels, 200 records) that mirrors the real distribution's *shape* (singleton-heavy, sparse, mixed prefixes).
- The unit, property, and benchmark layers — all distribution-shape-agnostic.

Local-only:
- The full 3,030-record CSV.
- The hand-curated golden cases.
- The A/B harness against real boundaries.

The synthetic data generator is itself code worth writing — `tests/fixtures/synth_collection.py` parametrized over distribution shape — so that algorithm regressions reproducible without the CSV.

---

## 8. Open Questions & Recommendations for the Planning Phase

### 8.1 Open questions (not answerable without owner input)

1. **Does the user's hand-arranged shelf follow catalog-# density or uniform spacing?** This is the binary that picks between §4.1 (uniform) and §4.10 (gap-weighted). The only way to answer is for the owner to hand-curate ~20 records' true positions and compare. **Decision input the planning phase should ask the owner to produce.**

2. **For multi-prefix labels (34.8% of multi-record labels), does the owner shelve all prefixes together or in prefix-grouped sub-runs?** This affects whether the parser's prefix-discriminating sort is correct (`BLP 1, BLP 2, BST 1, BST 2` vs `BLP 1, BST 1, BLP 2, BST 2`). The CSV cannot answer this; the owner's eye on the shelf can. **Validate by inspection during the first reshuffle wizard run.**

3. **How does the owner treat the multi-value catalog field (e.g., `BLP-100, BST-200`)?** As "this record's catalog# is `BLP-100`" (first-value), or as "this record is sortable under either" (and the owner has chosen one based on the physical pressing)? The CSV's column is identical to Discogs' multi-cat# concatenation, so this is ambiguous in data.

4. **How does the owner treat the multi-label field (18.9% of records)?** Are these shelved under the first label only, or under whichever label's catalog# is more prominent? Default assumption: first-label, matching CSV order — verify with the owner.

5. **Is there a confidence threshold below which the UI should show *no* sub-cube highlight at all (just the cube)?** The contract supports `sub_cube_interval: None`. The threshold is a UX decision feeding back into the algorithm choice — strict thresholds favor §4.8 fallback more often.

### 8.2 Recommended planning-phase actions

1. **Build the parser first** (§3, ~1 day). It is shared infrastructure: the boundary save validator depends on it, every algorithm depends on it, every test depends on it. Implementing the wrong parser invalidates every other measurement.

2. **Implement two algorithms initially: §4.1 (index) and §4.8 (no-interp).** Together they form a useful product floor: §4.1 covers all the cases where the algorithm matters, §4.8 is the timeout fallback. Ship that, observe behavior on real queries, then iterate.

3. **Build the A/B harness (§7.4) before committing to any further algorithm.** It is the only thing that turns "which algorithm is best?" from speculation into measurement.

4. **Defer §4.10 (density-weighted) until §4.1 has been observed in practice for a few weeks.** If sub-cube positions feel off on sparse labels — the largest data category — §4.10 is the obvious next experiment. If §4.1 already feels right, the extra complexity is wasted.

5. **Hard-no on §4.7 (lookup table)** unless profiling shows a need. The architecture's "position is computed, not stored" decision is load-bearing; reversing it adds operational moving parts (refresh triggers, version columns, race conditions) for a problem the benchmarks won't actually demonstrate.

6. **Hard-no on §4.5 (KNN) and §4.9 (isotonic)** for v1. Both are statistical sledgehammers; the data is too sparse (median k = 1) for the methods to materially outperform §4.1. Re-consider if the collection grows to tens of thousands.

7. **The tiered cascade (§5.1) is the realistic target architecture once v1 ships.** Start with §4.1 + §4.8; add the per-tier dispatcher once the test harness's per-shape error bars are visible.

8. **Confidence is part of the algorithm choice, not an afterthought.** Every candidate's section above implies a confidence formula (singleton = low; multi-prefix routed to index = medium; dense label with hybrid = high; timeout = zero). Treat the confidence calibration as part of the implementation work, not a sidecar.

### 8.3 Things that are *not* worth researching further at this stage

- **The exact threshold for "dense vs sparse" labels** — only relevant once the tiered cascade is being built. Pick a reasonable value (e.g., density ≥ 0.3) and tune via the A/B harness.
- **Whether to use `natsort` or a custom parser** — both are demonstrably workable. Pick whichever the implementer finds easier to read and pin behavior with tests.
- **Locale-aware sort** — the user is English-language and the CSV is ASCII-clean. NFKC normalization handles the rare Unicode edge case; full ICU collation adds weight without observable benefit.

---

## 9. References & Sources

### Authoritative

- **`PROJECT.md`** (this repo) — Position-estimation is its own research stream; deterministic ordering invariant. HIGH.
- **`.planning/research/ARCHITECTURE.md`** §Position-Estimator Contract — input/output/error/latency contract. HIGH.
- **`.planning/research/PITFALLS.md`** Pitfall 1 — catalog-number string comparison silently breaks natural sort; normalization stages and Hypothesis property requirement. HIGH.
- **`.planning/research/STACK.md`** §Testing the Position-Estimation Algorithm — recommended harness (pytest, Hypothesis, pytest-benchmark). HIGH.
- **`RWlodarczyk-collection-20260519-0257.csv`** (local-only, gitignored) — aggregate statistics in §2 computed directly. HIGH.

### Catalog-number parsing

- [natsort on PyPI](https://pypi.org/project/natsort/) — natural-sort library, latest 8.4.x (April 2025), `natsort_keygen(alg=ns.IGNORECASE | ns.SIGNED)` is the relevant API. HIGH.
- [natsort docs](https://natsort.readthedocs.io/) — `ns` algorithm flags, including `IGNORECASE`, `LOCALE`, `SIGNED`. HIGH.
- [natsort GitHub](https://github.com/SethMMorton/natsort) — splits strings into numbers/non-numbers using regexes; algorithm parameters combine with bitwise OR. HIGH.
- [Discogs Database Guidelines 4: Label / Catalog Number](https://support.discogs.com/hc/en-us/articles/360005006614-Database-Guidelines-4-Label-Catalog-Number) — catalog numbers entered as they appear; variations stored as separate fields. MEDIUM.
- [Discogs Reference Wiki — Identifying catalog and other numbers on a release](https://reference.discogs.com/wiki/identifying-catalog-and-other-numbers-on-a-release) — barcode-as-catalog# pattern. MEDIUM.

### Algorithm methodology

- [Isotonic regression — Wikipedia](https://en.wikipedia.org/wiki/Isotonic_regression) — Pool Adjacent Violators algorithm; relevant to §4.9 and §5.2 monotone safety net. MEDIUM.
- [Stat 8054 Lecture Notes: Isotonic Regression](https://www.stat.umn.edu/geyer/8054/notes/isotonic.html) — algorithmic detail on PAV; relevant if §4.9 is ever pursued. MEDIUM.

### Statistical fitness for purpose

- Computed from the local CSV (no external link). The "median records per label = 1", "57% sparse multi-record labels", "35.6% raw-vs-natural sort divergence", and "no label is large enough to fill a cube" findings are first-party measurements. HIGH (computed directly).

---

*Position-estimation research for: GRUVAX (sub-cube position interpolation, ~3,030 records across 32 cubes, parser + comparator + algorithm).*
*Researched: 2026-05-18*

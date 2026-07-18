# ADR-0001: Single normalization & ordering authority for labels and catalog numbers

- **Status:** Accepted
- **Date:** 2026-07-17
- **Decider:** Robert (owner), via planning session
- **Provenance:** Adopted from promoted bug-hunt report `gruvax-icc5` (origin: report, filed by `disp/bug-hunt`); folds in the related normalization-family bugs `gruvax-p1g`, `gruvax-pjyz`, `gruvax-raz`, `gruvax-efe`.

## Context

The bug hunt confirmed a class of defects with one root cause: **multiple, disagreeing
normalization/ordering authorities** for the two strings GRUVAX's core value depends on —
record label and catalog number.

- **Ordering (gruvax-icc5, P0):** the admin label picker orders labels with Postgres's
  linguistic collation (`en_US.utf8`/glibc, punctuation-ignoring), while the estimator's
  `_cut_key` compares Python codepoint order. There is no collation under which the two agree
  (verified: 4/6 cubes mis-lit with real vinyl labels — A&M, Blue Note). Silent wrong-cube
  lighting at full confidence.
- **Catalog identity (gruvax-pjyz):** the estimator NFKC-folds catalog numbers
  (`parse_key`), but sync ingest stores them verbatim and search normalizes with `lower()`
  only — a full-width catalog is shelved correctly yet unfindable by ASCII query.
- **Casefold boundary (gruvax-p1g):** override labels are casefolded inconsistently at the
  storage boundary — case-variant duplicate PK rows, heap-order-dependent estimates,
  casefolded strings leaking into the admin UI.
- **Key construction (gruvax-raz):** the digit cap in `parse_key` truncates instead of
  saturating — 13+-digit catalogs invert order and collapse keys.
- **Query hygiene (gruvax-efe):** `%` survives input normalization into a LIKE pattern.

## Decision

**Python is the single authority for label ordering and catalog normalization.** Postgres
stores and retrieves; it no longer defines ordering or string identity.

1. **One module owns the transforms** — a collation/normalization authority in the estimator
   package exposes:
   - `label_sort_key(label)` — casefold + **pyuca** (Unicode Collation Algorithm, pure
     Python) sort key. Used by *both* the admin label picker (`get_distinct_labels` sorts in
     Python; the SQL `ORDER BY` stops being load-bearing) and the estimator's cut-key
     comparison. The two orders agree by construction.
   - `normalize_catalog(raw)` — the NFKC + separator/case fold the estimator's `parse_key`
     already applies, exported for reuse at sync ingest so the stored value, the FTS index,
     and the estimator agree on catalog identity.
2. **pyuca over PyICU / PG-side ordering.** pyuca is pure Python (no C dependency in the
   slim Docker image or on the Pi), fast enough for ~hundreds of labels, and its bundled
   DUCET tables make ordering **deterministic across environments and upgrades** — staleness
   relative to the latest Unicode is acceptable for record-label names and is effectively a
   stability feature. PyICU was rejected for build/image weight; PG-side ordinal ranks were
   rejected because they couple `derive()` to the DB and PG exposes no sort keys.
3. **Divergence fails loudly.** The derive-time monotonicity guard (introduced with
   gruvax-trl) is retained: if cut keys are not monotonic in physical shelf order — e.g. a
   layout laid out under the old Postgres order that pyuca orders differently — the derive
   emits a loud warning surfaced to the admin instead of silently mis-lighting.
4. **One casefold boundary for override labels** — override storage keys are normalized
   (casefolded) uniformly at every write site; original-case display strings are carried
   separately for the UI. Existing case-variant duplicate rows are deduplicated by
   migration.

## Consequences

- New runtime dependency: `pyuca` (pinned). Pure Python; no image changes.
- `get_distinct_labels` sorts in Python; label lists must flow through the authority module.
  Any future "sort labels" site must use `label_sort_key` — enforced by convention and by
  the picker/estimator agreement property test.
- Existing shelf layouts laid out under the glibc picker order may trip the monotonicity
  guard once pyuca ordering takes effect; the admin re-confirms those cut points once. This
  is deliberate: visible one-time friction over silent mis-lighting.
- A backfill migration renormalizes stored `catalog_number` values (NFKC), regenerating the
  FTS vector via the existing generated column.
- Implementation is tracked by the "normalization authority" molecule filed from this ADR
  (epic supersedes standalone beads gruvax-p1g / pjyz / raz / efe; gruvax-icc5 closes as
  adopted into the epic).

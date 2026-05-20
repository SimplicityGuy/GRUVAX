"""Phase 1 + Phase 2 position estimators for GRUVAX.

Phase 1: cube-only fallback (INTERPOLATION.md §4.8) — ``locate_cube_only``.
Phase 2: index-based estimator (INTERPOLATION.md §4.1) — ``locate_by_index`` +
  ``locate`` dispatcher that falls back to §4.8 when confidence is too low.

Decisions implemented:
  D-10: sub_cube_interval is None in cube-only-v1; populated by index-v1.
  D-11: confidence is a float constant CUBE_ONLY_CONFIDENCE = 0.30 for cube-only.
  D-12: label_span contains ALL covering cubes; primary_cube is None when no
        boundary covers the label (confidence 0.0, not an exception).
  D-13: all catalog comparisons use parse_key from normalize.py (POS-01);
        raw string comparison is forbidden.

CUBE-10 / D-02 RECONCILIATION (kept here for traceability):
  REQUIREMENTS.md CUBE-10 literal wording is "tick-mark indicator rather than a
  width-proportional range bar". Per D-02 the owner overrides this to a faint
  full-cube band — so singletons return SubInterval(start=0.0, end=1.0), NEVER a
  zero-width/tick bar (Pitfall 21). Non-singletons use the ±POSITION_HALF_WIDTH
  band, also never zero-width.
"""

from __future__ import annotations

from gruvax.estimator.boundary_cache import BoundaryCache
from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow
from gruvax.estimator.constants import POSITION_HALF_WIDTH, compute_confidence
from gruvax.estimator.contract import (
    CUBE_ONLY_CONFIDENCE,
    NO_BOUNDARY_CONFIDENCE,
    CubeRef,
    LocateResult,
    SubInterval,
)
from gruvax.estimator.normalize import catalog_in_range, parse_key

# Re-export constants so tests can import them from algorithm.py
__all__ = [
    "CUBE_ONLY_CONFIDENCE",
    "NO_BOUNDARY_CONFIDENCE",
    "locate",
    "locate_by_index",
    "locate_cube_only",
]


def locate_cube_only(
    release_id: int,
    label: str,
    catalog_number: str,
    cache: BoundaryCache,
) -> LocateResult:
    """Find the covering cube(s) for a record using boundary lookup only.

    Returns a ``LocateResult`` with:
      - ``confidence == CUBE_ONLY_CONFIDENCE`` (0.30) when at least one boundary
        covers (label, catalog_number) — see D-11.
      - ``confidence == NO_BOUNDARY_CONFIDENCE`` (0.0) and ``primary_cube = None``
        when no boundary covers the label — see D-12.
      - ``sub_cube_interval = None`` always (Phase 1 cube-only) — see D-10.
      - ``label_span`` sorted by (unit_id, row, col); ``primary_cube = label_span[0]``.

    Covering semantics (boundary row b covers record iff):
      1. b.first_label.casefold() <= label.casefold() <= b.last_label.casefold()
      2. catalog_in_range(catalog_number, b.first_catalog, b.last_catalog)

    Both conditions must hold. Condition 2 uses ``catalog_in_range`` from
    ``normalize.py`` — raw string comparison is forbidden (POS-01 / T-01-04).

    Error semantics per ARCHITECTURE.md:
      - release_id not in collection → the caller (API layer) returns HTTP 404.
        This function is never called for out-of-collection release IDs.
      - No boundary covers label → returns confidence 0.0, primary_cube None,
        label_span []. The API layer returns HTTP 200 with this payload (D-12).

    Args:
        release_id: The Discogs release ID (propagated into LocateResult).
        label: The record's label string (e.g. ``"Blue Note"``).
        catalog_number: The record's catalog number (e.g. ``"BLP 4195"``).
        cache: A populated BoundaryCache (loaded at startup).

    Returns:
        A LocateResult with the cube-only-v1 estimate.
    """
    covering: list[CubeRef] = []

    for b in cache.get_boundaries():
        # Skip empty cubes — they have no meaningful label range.
        if b.is_empty or b.first_label is None or b.last_label is None:
            continue

        # Label range check (case-folded, not the POS-01 normalizer — labels are
        # not catalog numbers and must not have separators collapsed).
        if not (b.first_label.casefold() <= label.casefold() <= b.last_label.casefold()):
            continue

        # Catalog range check — MUST use catalog_in_range (POS-01 / T-01-04).
        if not catalog_in_range(catalog_number, b.first_catalog, b.last_catalog):
            continue

        covering.append(CubeRef(unit_id=b.unit_id, row=b.row, col=b.col))

    if not covering:
        return LocateResult(
            release_id=release_id,
            primary_cube=None,
            label_span=[],
            sub_cube_interval=None,
            confidence=NO_BOUNDARY_CONFIDENCE,
        )

    # Sort by (unit_id, row, col) so primary_cube is deterministic.
    sorted_span = sorted(covering, key=lambda c: (c.unit_id, c.row, c.col))

    return LocateResult(
        release_id=release_id,
        primary_cube=sorted_span[0],
        label_span=sorted_span,
        sub_cube_interval=None,
        confidence=CUBE_ONLY_CONFIDENCE,
    )


def locate_by_index(
    release_id: int,
    label: str,
    catalog_number: str,
    cache: BoundaryCache,
    snapshot: CollectionSnapshot,
) -> LocateResult:
    """§4.1 index-based estimator: compute sub-cube position from sorted label index.

    CUBE-10 / D-02 RECONCILIATION: singletons (k=1) return a faint full-cube band
    (start=0.0, end=1.0) as specified by the owner's D-02 override, NOT a zero-width
    tick mark as per the CUBE-10 literal wording. Non-singletons use ±POSITION_HALF_WIDTH
    (Pitfall 21 — never zero-width).

    Algorithm:
      1. Delegate to locate_cube_only for primary_cube/label_span/no-boundary handling.
      2. If no covering boundary (primary_cube is None), return locate_cube_only result.
      3. Pull label_records from snapshot; sort by parse_key (D-13 — no raw string sort).
      4. SPECIAL-CASE singletons (k=1) FIRST (Pitfall A: k-1 == 0 → ZeroDivisionError).
         Return SubInterval(start=0.0, end=1.0) with confidence CUBE_ONLY_CONFIDENCE.
      5. For k>1: find idx of this release_id in sorted_recs (Pitfall B: may be None).
         If None → fall back to locate_cube_only result.
      6. Compute fractional position f = idx / (k-1).
      7. Apply band formula: start = max(0.0, f - POSITION_HALF_WIDTH),
                              end   = min(1.0, f + POSITION_HALF_WIDTH).
      8. Multi-cube-span handling: map f across label_span, detect boundary crossing.
      9. Set confidence = compute_confidence(k), estimator_version = "index-v1".

    Args:
        release_id: The Discogs release ID.
        label: Record label string.
        catalog_number: Record catalog number.
        cache: Populated BoundaryCache for cube boundary lookup.
        snapshot: Populated CollectionSnapshot for label record index lookup.

    Returns:
        A LocateResult with sub_cube_interval populated when coverage exists.
    """
    # Step 1: Delegate to locate_cube_only for boundary coverage.
    cube_only_result = locate_cube_only(
        release_id=release_id,
        label=label,
        catalog_number=catalog_number,
        cache=cache,
    )

    # Step 2: No covering boundary → return cube_only result unchanged.
    if cube_only_result.primary_cube is None:
        return cube_only_result

    primary_cube = cube_only_result.primary_cube
    label_span = cube_only_result.label_span

    # Step 3: Pull label records from snapshot and sort by parse_key (D-13).
    label_records: list[RecordRow] = snapshot.get_label_records(label)
    sorted_recs = sorted(label_records, key=lambda r: parse_key(r.catalog_number))
    k = len(sorted_recs)

    # Step 4: Singleton special case (Pitfall A — avoids k-1 == 0 ZeroDivisionError).
    # D-02: owner overrides CUBE-10; singleton = faint full-cube band, not tick mark.
    if k == 1:
        sub_interval = SubInterval(
            cube=primary_cube,
            start=0.0,
            end=1.0,
            crosses_boundary=False,
        )
        return LocateResult(
            release_id=release_id,
            primary_cube=primary_cube,
            label_span=label_span,
            sub_cube_interval=sub_interval,
            confidence=CUBE_ONLY_CONFIDENCE,  # D-02: singleton confidence stays at 0.30
            estimator_version="index-v1",
        )

    # Step 5: Find this record's index in the sorted list (Pitfall B: may be missing).
    idx: int | None = next(
        (i for i, r in enumerate(sorted_recs) if r.release_id == release_id),
        None,
    )
    if idx is None:
        # Record not in snapshot (stale snapshot / Pitfall B) → fall back to cube-only.
        return locate_cube_only(
            release_id=release_id,
            label=label,
            catalog_number=catalog_number,
            cache=cache,
        )

    # Step 6: Fractional position within the label's ordered range.
    f: float = idx / (k - 1)

    # Step 7 + 8: Band formula and multi-cube-span handling.
    crosses_boundary = False
    next_cube: CubeRef | None = None

    if len(label_span) > 1:
        # Multi-cube label: map f across label_span to find which cube f falls in.
        span_idx = min(len(label_span) - 1, int(f * len(label_span)))
        chosen_cube = label_span[span_idx]

        # Within-cube fraction: recompute f relative to the chosen cube's slice.
        slice_width = 1.0 / len(label_span)
        within_f = (f - span_idx * slice_width) / slice_width

        # Apply band formula within chosen cube.
        start = max(0.0, within_f - POSITION_HALF_WIDTH)
        end = min(1.0, within_f + POSITION_HALF_WIDTH)

        # Detect boundary crossing: band extends past cube's right edge.
        if end >= 1.0 and span_idx + 1 < len(label_span):
            crosses_boundary = True
            next_cube = label_span[span_idx + 1]

        sub_interval = SubInterval(
            cube=chosen_cube,
            start=start,
            end=end,
            crosses_boundary=crosses_boundary,
            next_cube=next_cube,
        )
    else:
        # Single-cube label: apply band formula directly.
        # EXACT BAND FORMULA (D-01/Pitfall 21 — never zero-width):
        start = max(0.0, f - POSITION_HALF_WIDTH)
        end = min(1.0, f + POSITION_HALF_WIDTH)
        sub_interval = SubInterval(
            cube=primary_cube,
            start=start,
            end=end,
            crosses_boundary=False,
        )

    # Step 9: Calibrated confidence from record count k.
    confidence = compute_confidence(k)

    return LocateResult(
        release_id=release_id,
        primary_cube=primary_cube,
        label_span=label_span,
        sub_cube_interval=sub_interval,
        confidence=confidence,
        estimator_version="index-v1",
    )


def locate(
    release_id: int,
    label: str,
    catalog_number: str,
    cache: BoundaryCache,
    snapshot: CollectionSnapshot,
) -> LocateResult:
    """Dispatcher: §4.1 index-based estimator with §4.8 cube-only fallback.

    Routes to locate_by_index when the snapshot has records for the label, and
    falls back to locate_cube_only when:
      - The snapshot has no records for the label (stale snapshot or unknown label)
      - locate_by_index produces confidence <= CUBE_ONLY_CONFIDENCE (edge case)

    The fallback path always sets estimator_version = "cube-only-v1" and
    sub_cube_interval = None for a clean §4.8 response.

    Args:
        release_id: The Discogs release ID.
        label: Record label string.
        catalog_number: Record catalog number.
        cache: Populated BoundaryCache for cube boundary lookup.
        snapshot: Populated CollectionSnapshot for label record index lookup.

    Returns:
        A LocateResult from either §4.1 (preferred) or §4.8 (fallback).
    """
    # No snapshot records for this label → fall back to §4.8 cube-only.
    if not snapshot.get_label_records(label):
        result = locate_cube_only(
            release_id=release_id,
            label=label,
            catalog_number=catalog_number,
            cache=cache,
        )
        result.estimator_version = "cube-only-v1"
        return result

    # Try §4.1 index-based estimator.
    result = locate_by_index(
        release_id=release_id,
        label=label,
        catalog_number=catalog_number,
        cache=cache,
        snapshot=snapshot,
    )

    # If confidence is at or below the cube-only threshold, strip sub_cube_interval.
    if result.confidence <= CUBE_ONLY_CONFIDENCE:
        return LocateResult(
            release_id=release_id,
            primary_cube=result.primary_cube,
            label_span=result.label_span,
            sub_cube_interval=None,
            confidence=result.confidence,
            estimator_version="cube-only-v1",
        )

    return result

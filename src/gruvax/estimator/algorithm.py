"""Phase 1 + Phase 5 position estimators for GRUVAX.

Phase 1: cube-only fallback (INTERPOLATION.md §4.8) — ``locate_cube_only``.
Phase 5: segment-aware two-level interpolation — ``locate_by_segment`` (replaces §4.1).
  ``locate_by_index`` is RETIRED from the public API.
  ``locate`` dispatcher updated to call ``locate_by_segment``.
  estimator_version = "segment-v1".

Decisions implemented:
  D-01: §4.1 retired — ``locate_by_segment`` is the sole index estimator.
        ``_locate_by_index_v1`` retained ONLY for the D-02 regression test, not in ``__all__``.
        estimator_version bumped to "segment-v1" for the segment path while §4.8
        cube-only stays the fallback ("cube-only-v1").
  D-02: §4.1 regression invariant — single-segment bin reproduces §4.1 exactly
        (within 1e-6). Tested by test_single_segment_bin_reproduces_v1_index which
        imports ``_locate_by_index_v1`` by name from this module (private, not in __all__).
  D-10: sub_cube_interval is None in cube-only-v1; populated by segment-v1.
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

§4.1 BASELINE RETENTION DECISION (D-02 / Warning 2):
  The public estimator is ``locate_by_segment``. ``locate_by_index`` has been
  removed from the public API and from ``__all__``. The retired §4.1 implementation
  is preserved IN-PLACE as the private function ``_locate_by_index_v1`` — used ONLY
  by the D-02 regression test ``test_single_segment_bin_reproduces_v1_index``.
  DO NOT use ``_locate_by_index_v1`` in production code.
"""

from __future__ import annotations

from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow
from gruvax.estimator.constants import (
    POSITION_HALF_WIDTH,
    SEGMENT_ESTIMATOR_VERSION,
    compute_confidence,
)
from gruvax.estimator.contract import (
    CUBE_ONLY_CONFIDENCE,
    NO_BOUNDARY_CONFIDENCE,
    CubeRef,
    LocateResult,
    SubInterval,
)
from gruvax.estimator.normalize import parse_key
from gruvax.estimator.segment_cache import SegmentCache

# Re-export constants so tests can import them from algorithm.py
__all__ = [
    "CUBE_ONLY_CONFIDENCE",
    "NO_BOUNDARY_CONFIDENCE",
    "locate",
    "locate_by_segment",
    "locate_cube_only",
]


def locate_cube_only(
    release_id: int,
    label: str,
    catalog_number: str,
    segment_cache: SegmentCache,
    snapshot: CollectionSnapshot,
) -> LocateResult:
    """§4.8 fallback: find covering bin via SegmentCache (Phase 5 — replaces last_* check).

    Returns a ``LocateResult`` with:
      - ``confidence == CUBE_ONLY_CONFIDENCE`` (0.30) when a bin covers this record
        (i.e. segment_cache.get_segment_for_rank returns a result) — see D-11.
      - ``confidence == NO_BOUNDARY_CONFIDENCE`` (0.0) and ``primary_cube = None``
        when no bin covers the label — see D-12.
      - ``sub_cube_interval = None`` always (§4.8 cube-only) — see D-10.
      - ``label_span`` sorted by (unit_id, row, col); ``primary_cube = label_span[0]``.

    Coverage semantics (Phase 5 — last_* dropped from BoundaryRow):
      1. Get label records from snapshot; sort by parse_key.
      2. Find row-rank of this release_id.
      3. Call segment_cache.get_segment_for_rank(label, rank).
      4. A bin covers this record iff rank falls within a segment's rank range.
         All bins for the label are found via get_bins_for_label.

    Error semantics per ARCHITECTURE.md:
      - release_id not in collection → the caller (API layer) returns HTTP 404.
        This function is never called for out-of-collection release IDs.
      - No boundary covers label → returns confidence 0.0, primary_cube None,
        label_span []. The API layer returns HTTP 200 with this payload (D-12).

    Args:
        release_id: The Discogs release ID (propagated into LocateResult).
        label: The record's label string (e.g. ``"Blue Note"``).
        catalog_number: The record's catalog number (e.g. ``"BLP 4195"``).
        segment_cache: A populated SegmentCache (derived at startup).
        snapshot: A populated CollectionSnapshot.

    Returns:
        A LocateResult with the cube-only-v1 estimate.
    """
    # Step 1: Sort label records by parse_key (D-13 — no raw string sort).
    label_records: list[RecordRow] = snapshot.get_label_records(label)
    sorted_recs = sorted(label_records, key=lambda r: parse_key(r.catalog_number))

    # Step 2: Find row-rank of this release_id (may be None if not in snapshot).
    rank: int | None = next(
        (i for i, r in enumerate(sorted_recs) if r.release_id == release_id),
        None,
    )

    if rank is None:
        # Not in snapshot (stale or unknown) → no boundary
        return LocateResult(
            release_id=release_id,
            primary_cube=None,
            label_span=[],
            sub_cube_interval=None,
            confidence=NO_BOUNDARY_CONFIDENCE,
        )

    # Step 3: Get the bin for this rank via SegmentCache.
    result = segment_cache.get_segment_for_rank(label, rank)

    if result is None:
        # No segment found for this label/rank → no boundary
        return LocateResult(
            release_id=release_id,
            primary_cube=None,
            label_span=[],
            sub_cube_interval=None,
            confidence=NO_BOUNDARY_CONFIDENCE,
        )

    # Record is covered. Build label_span from all bins for this label.
    # Sort by (unit_id, row, col) so primary_cube is deterministic.
    label_bins = segment_cache.get_bins_for_label(label)
    covering = sorted(
        [CubeRef(unit_id=b.unit_id, row=b.row, col=b.col) for b in label_bins],
        key=lambda c: (c.unit_id, c.row, c.col),
    )

    if not covering:
        return LocateResult(
            release_id=release_id,
            primary_cube=None,
            label_span=[],
            sub_cube_interval=None,
            confidence=NO_BOUNDARY_CONFIDENCE,
        )

    return LocateResult(
        release_id=release_id,
        primary_cube=covering[0],
        label_span=covering,
        sub_cube_interval=None,
        confidence=CUBE_ONLY_CONFIDENCE,
    )


def locate_by_segment(
    release_id: int,
    label: str,
    catalog_number: str,
    segment_cache: SegmentCache,
    snapshot: CollectionSnapshot,
) -> LocateResult:
    """§4.1 replacement: two-level interpolation using SegmentCache (Phase 5 / SEG-06).

    Single-segment bin degeneracy (D-02 regression invariant):
      When a bin has exactly one LabelSegment, the formula reduces to:
        offset=0, fraction=1.0 → f = rank / (k-1) (or 0.5 midpoint for singleton)
      which is exactly the retired §4.1 formula. Verified by test_single_segment_bin_reproduces_v1_index.

    Algorithm:
      1. Get label records from snapshot; sort by parse_key (mirrors §4.1 step 3, D-13).
      2. Find row-rank of this release_id (mirrors §4.1 step 5 — fall back to cube-only if None).
      3. Call segment_cache.get_segment_for_rank(label, rank) → (bin, seg).
         If None → fall back to locate_cube_only result.
      4. offset = seg.offset_in_bin
      5. rank_in_segment = rank - seg.first_rank_in_label
      6. if seg.segment_count <= 1:
             f = offset + seg.applied_fraction * 0.5  # midpoint for singletons (D-02)
         else:
             f = offset + (rank_in_segment / (seg.segment_count - 1)) * seg.applied_fraction
      7. start = max(0.0, f - POSITION_HALF_WIDTH)
         end   = min(1.0, f + POSITION_HALF_WIDTH)
      8. Set crosses_boundary / next_cube on SubInterval when seg.continues is True (straddle).
      9. confidence = compute_confidence(len(sorted_recs))
         estimator_version = SEGMENT_ESTIMATOR_VERSION = "segment-v1"

    Args:
        release_id: The Discogs release ID.
        label: Record label string.
        catalog_number: Record catalog number.
        segment_cache: Populated SegmentCache for segment lookup.
        snapshot: Populated CollectionSnapshot for label record index lookup.

    Returns:
        A LocateResult with sub_cube_interval populated when coverage exists.
    """
    # Step 1: Sort label records by parse_key (D-13 — no raw string sort).
    label_records: list[RecordRow] = snapshot.get_label_records(label)
    sorted_recs = sorted(label_records, key=lambda r: parse_key(r.catalog_number))
    k = len(sorted_recs)

    # Step 2: Find row-rank of this release_id (may be None if not in snapshot).
    rank: int | None = next(
        (i for i, r in enumerate(sorted_recs) if r.release_id == release_id),
        None,
    )

    if rank is None:
        # Record not in snapshot (stale snapshot / Pitfall B) → fall back to cube-only.
        return locate_cube_only(
            release_id=release_id,
            label=label,
            catalog_number=catalog_number,
            segment_cache=segment_cache,
            snapshot=snapshot,
        )

    # Step 3: Find the bin + segment for this label's rank.
    seg_result = segment_cache.get_segment_for_rank(label, rank)

    if seg_result is None:
        # No segment for this rank → fall back to cube-only.
        return locate_cube_only(
            release_id=release_id,
            label=label,
            catalog_number=catalog_number,
            segment_cache=segment_cache,
            snapshot=snapshot,
        )

    bin_, seg = seg_result
    primary_cube = CubeRef(unit_id=bin_.unit_id, row=bin_.row, col=bin_.col)

    # Build label_span: all bins that have a segment for this label.
    label_bins = segment_cache.get_bins_for_label(label)
    label_span = sorted(
        [CubeRef(unit_id=b.unit_id, row=b.row, col=b.col) for b in label_bins],
        key=lambda c: (c.unit_id, c.row, c.col),
    )

    # Step 4+5: Compute two-level interpolation.
    offset = seg.offset_in_bin
    rank_in_segment = rank - seg.first_rank_in_label

    # Step 6: Two-level formula (D-02 singleton midpoint / Pitfall 21 never zero-width).
    if seg.segment_count <= 1:
        # Singleton within segment: use midpoint of the segment's applied_fraction span.
        f: float = offset + seg.applied_fraction * 0.5
    else:
        f = offset + (rank_in_segment / (seg.segment_count - 1)) * seg.applied_fraction

    # Step 7: Apply band formula (Pitfall 21 — never zero-width).
    start = max(0.0, f - POSITION_HALF_WIDTH)
    end = min(1.0, f + POSITION_HALF_WIDTH)

    # Step 8: Set crosses_boundary / next_cube when seg.continues is True.
    crosses_boundary = False
    next_cube: CubeRef | None = None

    if seg.continues:
        # Find the next bin in the label_span that comes after primary_cube.
        primary_idx = next(
            (
                i
                for i, c in enumerate(label_span)
                if c.unit_id == primary_cube.unit_id
                and c.row == primary_cube.row
                and c.col == primary_cube.col
            ),
            None,
        )
        if primary_idx is not None and primary_idx + 1 < len(label_span):
            crosses_boundary = True
            next_cube = label_span[primary_idx + 1]

    sub_interval = SubInterval(
        cube=primary_cube,
        start=start,
        end=end,
        crosses_boundary=crosses_boundary,
        next_cube=next_cube,
    )

    # Step 9: Calibrated confidence + segment estimator version.
    confidence = compute_confidence(k)

    return LocateResult(
        release_id=release_id,
        primary_cube=primary_cube,
        label_span=label_span,
        sub_cube_interval=sub_interval,
        confidence=confidence,
        estimator_version=SEGMENT_ESTIMATOR_VERSION,
    )


def _locate_by_index_v1(
    release_id: int,
    label: str,
    catalog_number: str,
    segment_cache: SegmentCache,
    snapshot: CollectionSnapshot,
) -> LocateResult:
    """§4.1 baseline — used ONLY by the D-02 regression test
    test_single_segment_bin_reproduces_v1_index; NOT a public estimator.

    This is the frozen §4.1 index-based implementation retained in-place for the
    D-02 regression invariant. It should never be called from production code.
    The test imports this private function explicitly by name from this module.

    Note: In Phase 5 the BoundaryCache no longer has last_* fields, so the old
    locate_cube_only coverage check has changed. For the D-02 invariant test to
    work correctly on a single-segment bin, this baseline implementation uses
    locate_cube_only (which now uses SegmentCache) for coverage, then applies
    the original §4.1 index-based formula for the sub-cube interval.

    §4.1 algorithm (verbatim from original locate_by_index):
      1. Delegate to locate_cube_only for primary_cube/label_span/no-boundary handling.
      2. If no covering boundary (primary_cube is None), return cube_only result.
      3. Pull label_records from snapshot; sort by parse_key (D-13).
      4. SPECIAL-CASE singletons (k=1) FIRST (Pitfall A: k-1 == 0 → ZeroDivisionError).
         Return SubInterval(start=0.0, end=1.0) with confidence CUBE_ONLY_CONFIDENCE.
      5. For k>1: find idx of this release_id in sorted_recs (Pitfall B: may be None).
         If None → fall back to locate_cube_only result.
      6. Compute fractional position f = idx / (k-1).
      7. Apply band formula: start = max(0.0, f - POSITION_HALF_WIDTH),
                              end   = min(1.0, f + POSITION_HALF_WIDTH).
      8. Multi-cube-span handling: map f across label_span, detect boundary crossing.
      9. Set confidence = compute_confidence(k), estimator_version = "index-v1".
    """
    # Step 1: Delegate to locate_cube_only for boundary coverage.
    cube_only_result = locate_cube_only(
        release_id=release_id,
        label=label,
        catalog_number=catalog_number,
        segment_cache=segment_cache,
        snapshot=snapshot,
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
            segment_cache=segment_cache,
            snapshot=snapshot,
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
    segment_cache: SegmentCache,
    snapshot: CollectionSnapshot,
) -> LocateResult:
    """Dispatcher: segment-aware estimator with §4.8 cube-only fallback (Phase 5).

    Routes to locate_by_segment when the snapshot has records for the label, and
    falls back to locate_cube_only when:
      - The snapshot has no records for the label (stale snapshot or unknown label)
      - locate_by_segment produces confidence <= CUBE_ONLY_CONFIDENCE (edge case)

    The fallback path always sets estimator_version = "cube-only-v1" and
    sub_cube_interval = None for a clean §4.8 response.

    Args:
        release_id: The Discogs release ID.
        label: Record label string.
        catalog_number: Record catalog number.
        segment_cache: Populated SegmentCache for segment lookup.
        snapshot: Populated CollectionSnapshot for label record index lookup.

    Returns:
        A LocateResult from either segment-v1 (preferred) or cube-only-v1 (fallback).
    """
    # No snapshot records for this label → fall back to §4.8 cube-only.
    if not snapshot.get_label_records(label):
        result = locate_cube_only(
            release_id=release_id,
            label=label,
            catalog_number=catalog_number,
            segment_cache=segment_cache,
            snapshot=snapshot,
        )
        result.estimator_version = "cube-only-v1"
        return result

    # Try segment-aware estimator.
    result = locate_by_segment(
        release_id=release_id,
        label=label,
        catalog_number=catalog_number,
        segment_cache=segment_cache,
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

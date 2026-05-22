"""Pure boundary-math helpers for fill-level, cube-contents, and midpoint suggestion.

Phase 5 changes:
  - ``count_records_in_bin`` replaces ``count_records_in_boundary`` and
    ``get_records_in_boundary``. Uses pre-derived LabelSegment.segment_count totals
    from SegmentCache — no snapshot or last_* needed.
  - ``get_records_in_boundary`` and ``count_records_in_boundary`` are RETIRED
    (used last_label/last_catalog which no longer exist in BoundaryRow, Phase 5).
  - ``sample_records`` and ``suggest_midpoint`` are unchanged — they operate on
    CollectionSnapshot records and do not reference BoundaryRow.last_*.
  - ``get_records_in_bin`` is provided as a snapshot-based record enumerator for
    units.py sample_records computation (slices bin segments from snapshot by rank).

Exported functions:
  - ``count_records_in_bin``   — count records in a bin using SegmentCache segment_counts
  - ``get_records_in_bin``     — return records in a bin by slicing snapshot by rank
  - ``sample_records``         — evenly-spaced index-stride sample of n records
  - ``suggest_midpoint``       — index-space midpoint between two anchor records

Key rules (from RESEARCH.md / CONTEXT.md):
  - Pitfall C (T-03-03): Labels compared with .casefold() ONLY — NEVER normalize_catalog().
    normalize_catalog() treats labels like catalog numbers (separators collapse, etc.)
    which produces wrong groupings (e.g., "Blue Note" → "bluenote").
  - Catalog comparisons ONLY via parse_key / catalog_in_range from normalize.py.
    Raw string compare is forbidden for catalogs (POS-01, T-01-04).
  - Midpoint is in INDEX space, not catalog-string space (Pitfall 22, D-08).
    The suggestion is always a real owned RecordRow from the snapshot.

Phase scope: These helpers are consumed by:
  - Phase 3: GET /api/cubes/{u}/{r}/{c} (fill_level + sample_records via SegmentCache)
  - Phase 3: POST /api/admin/cubes/validate (diff preview movement counts)
  - Phase 3: POST /api/admin/cubes/suggest (midpoint suggestion)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gruvax.estimator.normalize import parse_key

if TYPE_CHECKING:
    from gruvax.estimator.boundary_cache import BoundaryRow
    from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow
    from gruvax.estimator.segment_cache import SegmentBin


def count_records_in_boundary(
    boundary: BoundaryRow,
    snapshot: CollectionSnapshot,
) -> int:
    """DEPRECATED — Phase 5 compatibility shim (used by admin/cubes.py until 05-04).

    In Phase 5 BoundaryRow no longer has last_label/last_catalog, so this function
    cannot implement the old semantics. Returns 0 (safe fallback) until the admin
    write path is fully refactored in 05-04 to use SegmentCache/count_records_in_bin.

    This shim exists ONLY to keep admin/cubes.py compiling under mypy --strict
    during Wave 3 (05-03). It will be replaced in Wave 4 (05-04).
    """
    # BoundaryRow no longer has last_* fields (Phase 5 / SEG-01 migration 0005).
    # The admin write path (05-04) will replace this with count_records_in_bin(SegmentBin).
    # Return 0 as a safe fallback for now — admin movement counts will show 0 until 05-04.
    return 0


def count_records_in_bin(bin_: SegmentBin) -> int:
    """Count records in a bin using pre-derived LabelSegment.segment_count totals.

    Does NOT consult snapshot — counts come from SegmentCache's pre-derived values.
    Returns 0 for bins with no segments (is_empty or empty bin).

    This replaces the retired ``count_records_in_boundary`` which used
    ``last_label``/``last_catalog`` (Phase 5 cut-point model drops those fields).

    Args:
        bin_: SegmentBin from SegmentCache.

    Returns:
        Integer count of records in the bin. Never negative.
    """
    return sum(seg.segment_count for seg in bin_.segments)


def get_records_in_bin(
    bin_: SegmentBin,
    snapshot: CollectionSnapshot,
) -> list[RecordRow]:
    """Return all records belonging to a bin by slicing each segment's rank range.

    Iterates over the bin's LabelSegments, looks up each label's sorted records
    in the snapshot, and slices [first_rank_in_label, last_rank_in_label+1].
    Used by units.py ``get_cube`` for sample_records computation.

    Args:
        bin_: SegmentBin from SegmentCache.
        snapshot: CollectionSnapshot loaded from v_collection.

    Returns:
        List of RecordRow in the bin. Order: per-segment in segment order,
        records within each segment in parse_key sort order.
    """
    result: list[RecordRow] = []
    for seg in bin_.segments:
        # Get all records for this label sorted by parse_key (D-13).
        label_records = sorted(
            snapshot.get_label_records(seg.label),
            key=lambda r: parse_key(r.catalog_number),
        )
        # Slice the records that belong to this segment.
        seg_slice = label_records[seg.first_rank_in_label : seg.last_rank_in_label + 1]
        result.extend(seg_slice)
    return result


def sample_records(
    records_in_range: list[RecordRow],
    n: int = 7,
) -> list[RecordRow]:
    """Return n evenly-spaced records from the list using index-stride sampling.

    Sampling contract (RESEARCH.md Pattern 8):
      - [] for empty input
      - Identity (full list) when len(records_in_range) <= n
      - Exactly n records via index-stride: step = len/n,
        take records[int(i * step)] for i in range(n)

    All returned records are elements of the original input (real owned records).

    Args:
        records_in_range: List of RecordRow, typically all records in a bin.
        n: Target sample size (default 7, per D-14 / RESEARCH.md Pattern 8).

    Returns:
        Up to n records evenly distributed across the input list.
    """
    if not records_in_range:
        return []
    if len(records_in_range) <= n:
        return records_in_range

    step = len(records_in_range) / n
    return [records_in_range[int(i * step)] for i in range(n)]


def suggest_midpoint(
    label: str,
    first_anchor_release_id: int,
    last_anchor_release_id: int,
    snapshot: CollectionSnapshot,
) -> RecordRow | None:
    """Suggest the record at the index midpoint between two anchor records.

    Walks collection-INDEX space, NOT catalog-string space (Pitfall 22, D-08).
    The suggestion is always a real owned RecordRow from the snapshot — never
    a synthesized phantom string.

    Algorithm:
    1. Retrieve all records for the label and sort by parse_key(catalog_number).
    2. Find indices i_a and i_b of the two anchor release_ids.
    3. Compute mid = (i_a + i_b) // 2.
    4. Return records[mid] only if i_a < mid < i_b (strictly between).

    Returns None if:
      - Either anchor release_id is not in the snapshot for this label.
      - No record lies strictly between the two anchor indices.

    Args:
        label: The label shared by both anchor records.
        first_anchor_release_id: release_id of the cube's last record (lower anchor).
        last_anchor_release_id: release_id of the next cube's first record (upper anchor).
        snapshot: CollectionSnapshot loaded from v_collection.

    Returns:
        A RecordRow strictly between the two anchors in index space, or None.
    """
    records = sorted(
        snapshot.get_label_records(label),
        key=lambda r: parse_key(r.catalog_number),
    )
    if not records:
        return None

    # Find indices of the two anchors (O(n) — snapshot size is bounded by label)
    i_a: int | None = None
    i_b: int | None = None
    for idx, r in enumerate(records):
        if r.release_id == first_anchor_release_id:
            i_a = idx
        if r.release_id == last_anchor_release_id:
            i_b = idx

    if i_a is None or i_b is None:
        return None

    # Ensure anchors are in sorted order (swap if needed — caller may pass either order)
    if i_a > i_b:
        i_a, i_b = i_b, i_a

    mid = (i_a + i_b) // 2

    # Return midpoint only if strictly between anchors (Pitfall 22: not the anchors themselves)
    if i_a < mid < i_b:
        return records[mid]

    return None

"""Pure boundary-math helpers for fill-level, cube-contents, and midpoint suggestion.

These three functions operate entirely on in-memory data structures (BoundaryRow,
CollectionSnapshot) with no DB access, no I/O, and no side effects.

Exported functions:
  - ``count_records_in_boundary`` — count records in a boundary's label/catalog range
  - ``sample_records``            — evenly-spaced index-stride sample of n records
  - ``suggest_midpoint``          — index-space midpoint between two anchor records

Key rules (from RESEARCH.md / CONTEXT.md):
  - Pitfall C (T-03-03): Labels compared with .casefold() ONLY — NEVER normalize_catalog().
    normalize_catalog() treats labels like catalog numbers (separators collapse, etc.)
    which produces wrong groupings (e.g., "Blue Note" → "bluenote").
  - Catalog comparisons ONLY via parse_key / catalog_in_range from normalize.py.
    Raw string compare is forbidden for catalogs (POS-01, T-01-04).
  - Midpoint is in INDEX space, not catalog-string space (Pitfall 22, D-08).
    The suggestion is always a real owned RecordRow from the snapshot.

Phase scope: These helpers are consumed by:
  - Phase 3: GET /api/cubes/{u}/{r}/{c} (fill_level + sample_records)
  - Phase 3: POST /api/admin/cubes/validate (diff preview movement counts)
  - Phase 3: POST /api/admin/cubes/suggest (midpoint suggestion)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gruvax.estimator.normalize import catalog_in_range, parse_key

if TYPE_CHECKING:
    from gruvax.estimator.boundary_cache import BoundaryRow
    from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow


def get_records_in_boundary(
    boundary: BoundaryRow,
    snapshot: CollectionSnapshot,
) -> list[RecordRow]:
    """Return all records whose (label, catalog#) falls within the boundary's range.

    Returns [] for is_empty boundaries or boundaries with no first_label.

    Multi-label semantics (Open Question 4 / RESEARCH.md §Pattern 8):
      - Records of the FIRST label: catalog_number >= first_catalog (parse_key)
      - Records of any MIDDLE label (first_label < label < last_label by casefold):
        fully included (no catalog filter needed for middle labels)
      - Records of the LAST label: catalog_number <= last_catalog (parse_key)
      - For a same-label boundary (first_label == last_label):
        only records with catalog_number in [first_catalog, last_catalog] (parse_key)

    All label comparisons via .casefold() (Pitfall C — never normalize_catalog()).
    All catalog comparisons via parse_key / catalog_in_range (POS-01, T-03-03).

    Args:
        boundary: BoundaryRow from BoundaryCache.
        snapshot: CollectionSnapshot loaded from v_collection.

    Returns:
        List of RecordRow in the boundary's range. Empty list if is_empty or no
        first_label. Order reflects snapshot insertion order within each label group.
    """
    if boundary.is_empty or boundary.first_label is None:
        return []

    first_label_cf = (boundary.first_label or "").casefold()
    last_label_cf = (boundary.last_label or "").casefold()
    first_catalog = boundary.first_catalog
    last_catalog = boundary.last_catalog

    # Same-label boundary: simple catalog range check
    if first_label_cf == last_label_cf:
        records = snapshot.get_label_records(boundary.first_label)
        return [
            r
            for r in records
            if catalog_in_range(r.catalog_number, first_catalog, last_catalog)
        ]

    # Multi-label boundary: collect records across all labels in range
    result: list[RecordRow] = []
    for label_key, label_records in snapshot._by_label.items():
        if not label_records:
            continue

        sample_label_cf = label_key  # already casefolded in snapshot

        if sample_label_cf < first_label_cf or sample_label_cf > last_label_cf:
            continue

        if sample_label_cf == first_label_cf:
            # First label: only records with catalog >= first_catalog
            result.extend(
                r
                for r in label_records
                if parse_key(r.catalog_number) >= parse_key(first_catalog)
            )
        elif sample_label_cf == last_label_cf:
            # Last label: only records with catalog <= last_catalog
            result.extend(
                r
                for r in label_records
                if parse_key(r.catalog_number) <= parse_key(last_catalog)
            )
        else:
            # Middle label: fully included
            result.extend(label_records)

    return result


def count_records_in_boundary(
    boundary: BoundaryRow,
    snapshot: CollectionSnapshot,
) -> int:
    """Count records whose (label, catalog#) falls within the boundary's range.

    Delegates to ``get_records_in_boundary`` so count and sample share one pass.
    Returns 0 for is_empty boundaries or boundaries with no first_label.

    Args:
        boundary: BoundaryRow from BoundaryCache.
        snapshot: CollectionSnapshot loaded from v_collection.

    Returns:
        Integer count of records in the boundary's range. Never negative.
    """
    return len(get_records_in_boundary(boundary, snapshot))


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
        records_in_range: List of RecordRow, typically all records in a boundary.
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

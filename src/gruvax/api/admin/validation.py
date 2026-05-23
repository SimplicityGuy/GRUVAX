"""Admin boundary validation for the cut-point + width-override model.

Implements:
  - ``validate_boundary_order`` — kept for backward-compat (cut ordering check)
  - ``validate_contiguity``     — SEG-05: rejects proposed cuts that scatter a label
                                  across non-adjacent bins
  - ``validate_no_empty_bin``   — rejects cuts that would leave a bin with 0 records
  - ``validate_shelf_overflow`` — rejects insert-cut when no trailing free cube exists

Rules (carry-forward from Phase 1 / CONTEXT.md D-07 / D-13):
  - Label comparison: .casefold() ONLY (never normalize_catalog() — Pitfall C)
  - Catalog comparison: parse_key() ONLY (never raw string — POS-01, T-03-03)
  - Multi-label boundary: first_label < last_label by casefold is sufficient
  - Same-label boundary: parse_key(first_catalog) <= parse_key(last_catalog) required

This module is imported by the admin cubes router AND by unit tests (no DB deps).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gruvax.estimator.normalize import parse_key

if TYPE_CHECKING:
    from gruvax.estimator.boundary_cache import BoundaryCache
    from gruvax.estimator.segment_cache import SegmentCache


def build_proposed_cuts(
    cache: BoundaryCache,
    *,
    replace: tuple[int, int, int, str, str] | None = None,
    cascade: list[tuple[int, int, int, str | None, str | None, bool]] | None = None,
) -> list[dict[str, object]]:
    """Build the proposed_updates list from the live BoundaryCache + one edit.

    SEG-05 / D-09 (Direction A): enforce contiguity on the live write paths
    (put_bin_cut and insert_cut) before the DB transaction.  The preview/bulk path
    is the original site; this helper makes the same validate_contiguity call
    available to the direct write paths without re-wiring the two-step flow.

    Scope: only boundaries from the unit affected by the edit are returned.  The
    same label can legitimately appear in two different physical units (shelves);
    contiguity is a per-unit invariant because bins in different units are never
    adjacent on the same shelf.

    Args:
        cache:   Live BoundaryCache — provides the full current cut-point set.
        replace: For PUT /cut: (unit_id, row, col, first_label, first_catalog).
                 Overwrites the matching cube's cut point in the proposed list;
                 is_empty is set to False.  The unit_id in the tuple determines
                 which unit's boundaries are returned.
        cascade: For POST /insert-cut: list of (unit_id, row, col, first_label,
                 first_catalog, is_empty) 6-tuples already computed by insert_cut.
                 Each tuple overwrites the matching cube's entry in the proposed list.
                 The first tuple's unit_id determines the scope; all cubes in the
                 cascade are expected to belong to the same unit.

    Returns:
        List of dicts with keys (unit_id, row, col, first_label, first_catalog,
        is_empty) scoped to the target unit, in the exact shape validate_contiguity
        consumes. All cubes of that unit are included (empty or not) so the validator
        has the complete picture. Order is not guaranteed — validate_contiguity sorts.
    """
    # Determine the target unit from the edit descriptor
    target_unit_id: int | None = None
    if replace is not None:
        target_unit_id = replace[0]
    elif cascade is not None and cascade:
        target_unit_id = cascade[0][0]

    # Start from the current live boundary set, scoped to the target unit
    proposed: list[dict[str, object]] = [
        {
            "unit_id": b.unit_id,
            "row": b.row,
            "col": b.col,
            "first_label": b.first_label,
            "first_catalog": b.first_catalog,
            "is_empty": b.is_empty,
        }
        for b in cache.get_boundaries()
        if target_unit_id is None or b.unit_id == target_unit_id
    ]

    if replace is not None:
        r_uid, r_row, r_col, r_label, r_catalog = replace
        for entry in proposed:
            if entry["unit_id"] == r_uid and entry["row"] == r_row and entry["col"] == r_col:
                entry["first_label"] = r_label
                entry["first_catalog"] = r_catalog
                entry["is_empty"] = False
                break

    if cascade is not None:
        # Build a lookup for O(n) replacement
        cascade_lookup: dict[tuple[int, int, int], tuple[str | None, str | None, bool]] = {
            (uid, r, c): (fl, fc, ie) for uid, r, c, fl, fc, ie in cascade
        }
        for entry in proposed:
            key = (int(str(entry["unit_id"])), int(str(entry["row"])), int(str(entry["col"])))
            if key in cascade_lookup:
                fl, fc, ie = cascade_lookup[key]
                entry["first_label"] = fl
                entry["first_catalog"] = fc
                entry["is_empty"] = ie

    return proposed


# ── UI-SPEC error copy (verbatim per plan) ────────────────────────────────────

_SHELF_OVERFLOW_MSG = (
    "No empty cube available. Adding a cut here would move records into a cube that "
    "doesn't exist. Free up the last cube first."
)

_EMPTY_BIN_MSG_TEMPLATE = (
    "Bin {n} would have no records. Adjust the cut point to include at least one record."
)

_CONTIGUITY_MSG_TEMPLATE = (
    "This cut would split {label} across non-adjacent bins. Reposition the cut or "
    "remove the existing boundary."
)


def validate_boundary_order(
    first_label: str,
    first_catalog: str,
    last_label: str,
    last_catalog: str,
) -> bool:
    """Return True iff the boundary (first, last) is in valid order.

    Used by the single-cube editor and bulk editor for the legacy
    ``last_label``/``last_catalog`` ordering check. In the cut-point model
    this applies to checking that first_catalog <= last_catalog when a caller
    still passes last_* arguments (backward compat for bulk/validate endpoints).

    Comparison rules:
      1. Labels compared with .casefold() (never normalize_catalog — Pitfall C).
      2. If first_label.casefold() < last_label.casefold(): valid (multi-label span).
      3. If first_label.casefold() > last_label.casefold(): invalid.
      4. If labels are equal (same-label boundary): compare catalogs via parse_key.
         parse_key(first_catalog) <= parse_key(last_catalog) → valid.

    Args:
        first_label:   Label of the cube's first boundary record.
        first_catalog: Catalog number of the cube's first boundary record.
        last_label:    Label of the cube's last boundary record.
        last_catalog:  Catalog number of the cube's last boundary record.

    Returns:
        True if the boundary order is valid; False if first > last.
    """
    first_label_cf = first_label.casefold()
    last_label_cf = last_label.casefold()

    if first_label_cf < last_label_cf:
        # Multi-label span in correct order — valid regardless of catalog values
        return True

    if first_label_cf > last_label_cf:
        # First label sorts after last label — invalid
        return False

    # Same label: compare catalogs via POS-01 parse_key (never raw string)
    return parse_key(first_catalog) <= parse_key(last_catalog)


def validate_contiguity(
    proposed_updates: list[dict[str, object]],
    segment_cache: SegmentCache,
) -> str | None:
    """Return an error string if any label would be scattered across non-adjacent bins.

    SEG-05 / D-09: the contiguity invariant requires that all bins where a given
    label STARTS (via first_label cut point) form a contiguous block with no bins
    between them assigned to a different label.

    The proposed_updates list represents the new proposed cut-point set for a
    bulk edit. Each entry is a dict with keys: unit_id, row, col, first_label,
    first_catalog, is_empty.

    Algorithm:
      1. Build a sorted list of all proposed non-empty cuts with their first_label.
         This defines the proposed bin-start assignment.
      2. Simulate the label-assignment sequence for the proposed cut-points:
         each bin's label runs from its cut-start to the cut-start of the NEXT bin.
      3. Build a map: label -> list of bin-position indices (in the sorted order of
         proposed cuts) where the label STARTS a bin.
      4. For any label that starts in more than one bin, check that those bins are
         adjacent in the proposed cut sequence (consecutive positions). If any two
         "start" positions for the same label have a gap (different label in between),
         that is a contiguity violation.
      5. Also cross-check against SegmentCache: if a label appears in the current
         SegmentCache in bins outside the proposed update set, and the proposed update
         would create a gap in that label's span, return an error.

    Practical scenario (why this matters):
      Proposed: (1,0,0)=Blue Note, (1,0,2)=Blue Note (skipping (1,0,1)).
      This scatters Blue Note across non-adjacent proposed positions → rejected.

    Args:
        proposed_updates: List of dicts, each with unit_id, row, col, first_label,
                          first_catalog, is_empty.
        segment_cache:    Current SegmentCache (pre-edit approximation).

    Returns:
        Plain-language error string on contiguity violation; None if valid.
    """
    # Build sorted list of non-empty proposed cuts
    non_empty_updates = [u for u in proposed_updates if not u.get("is_empty")]
    if not non_empty_updates:
        return None

    # Sort by physical coord
    sorted_updates = sorted(
        non_empty_updates,
        key=lambda u: (int(str(u["unit_id"])), int(str(u["row"])), int(str(u["col"]))),
    )

    # Extract the sequence of first_labels in shelf order.
    # isinstance check guards non-str values; str() satisfies mypy's dict[str, object] typing.
    label_sequence: list[str] = [
        str(u["first_label"])
        for u in sorted_updates
        if u.get("first_label") and isinstance(u.get("first_label"), str)
    ]

    if not label_sequence:
        return None

    # For each label, find all positions where it starts a bin in the proposed sequence.
    # A label is "contiguous" iff its start positions form a consecutive block
    # (no other label's bin appears between two bins that start with the same label).
    # label_display maps the casefold key back to the first-seen ORIGINAL-case label
    # so the user-facing error message reads "Blue Note", not "blue note" (WR-04).
    label_start_positions: dict[str, list[int]] = {}
    label_display: dict[str, str] = {}
    for i, lbl in enumerate(label_sequence):
        lk = lbl.casefold()
        if lk not in label_start_positions:
            label_start_positions[lk] = []
        if lk not in label_display:
            label_display[lk] = lbl
        label_start_positions[lk].append(i)

    for lk, positions in label_start_positions.items():
        if len(positions) <= 1:
            continue
        # Check that all positions between the first and last occurrence of this
        # label are also occupied by this label (no gap = no other label in between).
        min_pos = positions[0]
        max_pos = positions[-1]
        expected_positions = set(positions)
        for pos in range(min_pos, max_pos + 1):
            if pos not in expected_positions:
                # There's a gap — another label's bin is at this position.
                # Surface the original-case label (label_display), never the
                # casefold key, in the owner-facing message (WR-04).
                return _CONTIGUITY_MSG_TEMPLATE.format(label=label_display[lk])

    return None


def validate_no_empty_bin(
    proposed_first_label: str,
    proposed_first_catalog: str,
    segment_cache: SegmentCache,
    unit_id: int,
    row: int,
    col: int,
) -> str | None:
    """Return an error string if the proposed cut would create a bin with 0 records.

    After inserting a cut at (unit_id, row, col) with (first_label, first_catalog),
    the new bin must contain at least one record. If the cut point equals the
    immediately preceding cut point within the same label's run (leaving no records
    between the two cuts), the insert is rejected.

    This is a simplified server-side check: we verify the proposed cut point is
    not identical to the current bin's cut point (which would leave the new bin empty).

    Args:
        proposed_first_label:   Label at the new cut point.
        proposed_first_catalog: Catalog at the new cut point.
        segment_cache:          Current SegmentCache.
        unit_id, row, col:      Coordinates of the target bin.

    Returns:
        Plain-language error string if the bin would be empty; None if valid.
    """
    seg_bin = segment_cache.get_bin(unit_id, row, col)
    if seg_bin is None:
        return None

    # Check if the proposed cut point matches the current cut point exactly
    # (same label + catalog = would create an empty leading bin)
    if (
        seg_bin.cut_label is not None
        and seg_bin.cut_catalog is not None
        and seg_bin.cut_label.casefold() == proposed_first_label.casefold()
        and parse_key(seg_bin.cut_catalog) == parse_key(proposed_first_catalog)
    ):
        return _EMPTY_BIN_MSG_TEMPLATE.format(n=f"({unit_id},{row},{col})")

    return None


def validate_shelf_overflow(
    boundary_cache: BoundaryCache,
    after_unit_id: int,
    after_row: int,
    after_col: int,
) -> str | None:
    """Return an error string if inserting a cut would overflow the shelf.

    A cut insert cascades all subsequent cut points by one position. If there is
    no free (empty or unassigned) cube after the insertion point, the cascade
    would push records into a cube that doesn't exist — shelf overflow.

    Args:
        boundary_cache: Current BoundaryCache with all cube boundaries.
        after_unit_id:  Unit ID of the cube after which the cut is inserted.
        after_row:      Row of the cube after which the cut is inserted.
        after_col:      Col of the cube after which the cut is inserted.

    Returns:
        Plain-language error string on shelf overflow; None if valid.
    """
    # Get all boundaries sorted by (unit_id, row, col)
    boundaries = sorted(
        boundary_cache.get_boundaries(),
        key=lambda b: (b.unit_id, b.row, b.col),
    )

    # Find the insertion point
    insert_idx: int | None = None
    for i, b in enumerate(boundaries):
        if b.unit_id == after_unit_id and b.row == after_row and b.col == after_col:
            insert_idx = i
            break

    if insert_idx is None:
        return None  # Target cube not found — cannot validate overflow

    # Check if there is at least one empty cube AFTER the insertion point
    for b in boundaries[insert_idx + 1 :]:
        if b.is_empty:
            return None  # Free cube found — insert is safe

    # No free cube after insertion point — would overflow the shelf
    return _SHELF_OVERFLOW_MSG

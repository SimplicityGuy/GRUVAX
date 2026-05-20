"""Phase 1 cube-only estimator for GRUVAX.

Implements the cube-only fallback from INTERPOLATION.md §4.8. This is the Phase 1
estimator; Phase 2 swaps in the §4.1 index-based estimator behind the same
LocateResult contract.

Decisions implemented:
  D-10: sub_cube_interval is always None (cube-only fallback).
  D-11: confidence is a float constant CUBE_ONLY_CONFIDENCE = 0.30.
  D-12: label_span contains ALL covering cubes; primary_cube is None when no
        boundary covers the label (confidence 0.0, not an exception).
  D-13: all catalog comparisons use catalog_in_range from normalize.py (POS-01);
        raw string comparison is forbidden.
"""

from __future__ import annotations

from gruvax.estimator.boundary_cache import BoundaryCache
from gruvax.estimator.contract import (
    CUBE_ONLY_CONFIDENCE,
    NO_BOUNDARY_CONFIDENCE,
    CubeRef,
    LocateResult,
)
from gruvax.estimator.normalize import catalog_in_range

# Re-export constants so tests can import them from algorithm.py
__all__ = ["CUBE_ONLY_CONFIDENCE", "NO_BOUNDARY_CONFIDENCE", "locate_cube_only"]


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

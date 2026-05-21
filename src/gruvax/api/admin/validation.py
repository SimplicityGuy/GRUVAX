"""POS-01 boundary order validation for admin cube editor.

Implements ``validate_boundary_order`` — the single legal comparison path for
checking that a cube's first boundary <= last boundary.

Rules (carry-forward from Phase 1 / CONTEXT.md D-07 / D-13):
  - Label comparison: .casefold() ONLY (never normalize_catalog() — Pitfall C)
  - Catalog comparison: parse_key() ONLY (never raw string — POS-01, T-03-03)
  - Multi-label boundary: first_label < last_label by casefold is sufficient (ordering
    is defined at label level for cross-label spans; within same label, catalog range applies)
  - Same-label boundary: parse_key(first_catalog) <= parse_key(last_catalog) required

This module is imported by the admin cubes router AND by unit tests (no DB deps).
"""

from __future__ import annotations

from gruvax.estimator.normalize import parse_key


def validate_boundary_order(
    first_label: str,
    first_catalog: str,
    last_label: str,
    last_catalog: str,
) -> bool:
    """Return True iff the boundary (first, last) is in valid order.

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

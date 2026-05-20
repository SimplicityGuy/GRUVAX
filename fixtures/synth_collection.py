"""Planted-truth synthetic collection factories for GRUVAX tests.

Plain Python module (NOT a pytest conftest) — importable from both:
  - tests/property/test_estimator_props.py (Hypothesis invariant tests)
  - scripts/run_all_algorithms.py (A/B harness, Plan 02-04)

Each factory returns a 3-tuple:
    (BoundaryCache, CollectionSnapshot, dict[int, float])

where the dict maps release_id → planted physical-shelf position fraction in [0, 1].

Pitfall F (CRITICAL): planted truth is the PHYSICAL shelf truth, NOT §4.1's own
formula. For uniform_dense the physical truth happens to equal idx/(k-1) — this
validates §4.1. For sparse_gappy the truth is gap-weighted cumulative fraction so
that §4.1 shows non-zero MAE while §4.8 (null → 0.5 midpoint) shows higher MAE.
This contrast is the point of the A/B harness in Plan 02-04.

All factories use the _load_rows / _load_snapshot seams — NO DB, NO async.
"""

from __future__ import annotations

from collections.abc import Callable

from gruvax.estimator.boundary_cache import BoundaryCache, BoundaryRow
from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow

# ── Internal helpers ──────────────────────────────────────────────────────────


def _build_cache(
    label: str,
    first_cat: str,
    last_cat: str,
    unit_id: int = 1,
    row: int = 0,
    col: int = 0,
) -> BoundaryCache:
    """Build a BoundaryCache with a single cube covering label + catalog range."""
    rows = [
        BoundaryRow(
            unit_id=unit_id,
            row=row,
            col=col,
            first_label=label,
            first_catalog=first_cat,
            last_label=label,
            last_catalog=last_cat,
            is_empty=False,
        )
    ]
    cache = BoundaryCache()
    cache._load_rows(rows)
    return cache


def _build_snapshot(label: str, catalog_numbers: list[str]) -> CollectionSnapshot:
    """Build a CollectionSnapshot from a label + sorted catalog number list.

    release_ids are assigned as 1-indexed sequential ints.
    """
    snapshot = CollectionSnapshot()
    records = [
        RecordRow(
            release_id=i + 1,
            label=label,
            catalog_number=cat,
        )
        for i, cat in enumerate(catalog_numbers)
    ]
    by_label: dict[str, list[RecordRow]] = {label.casefold(): records}
    snapshot._load_snapshot(by_label)
    return snapshot


# ── Shape factories ───────────────────────────────────────────────────────────


def make_uniform_dense() -> tuple[BoundaryCache, CollectionSnapshot, dict[int, float]]:
    """Uniform-dense label: k=20 records with evenly-spaced catalog numbers.

    Planted truth = idx/(k-1) — exactly §4.1's formula, so §4.1 shows ~0 MAE.
    §4.8 (null → midpoint 0.5 default) shows ~0.25 MAE for records near edges.

    Returns:
        (cache, snapshot, truth) where truth maps release_id → shelf position fraction.
    """
    label = "UniformDense"
    k = 20
    # Catalog numbers: UD 001 through UD 020
    catalogs = [f"UD {i:03d}" for i in range(1, k + 1)]
    cache = _build_cache(label, catalogs[0], catalogs[-1])
    snapshot = _build_snapshot(label, catalogs)

    # Pitfall F: planted truth IS idx/(k-1) for uniform-dense (validates §4.1)
    truth = {i + 1: i / (k - 1) for i in range(k)}
    return cache, snapshot, truth


def make_sparse_gappy() -> tuple[BoundaryCache, CollectionSnapshot, dict[int, float]]:
    """Sparse-gappy label: k=8 records with uneven gaps between catalog numbers.

    Pitfall F (CRITICAL): planted truth is gap-weighted cumulative fraction, NOT
    idx/(k-1). This means §4.1 will show non-zero MAE (because it assumes uniform
    distribution) while §4.8 (null → midpoint 0.5) shows higher MAE. The A/B
    harness in Plan 02-04 uses this to compare the two estimators empirically.

    The physical shelf positions are computed from the numeric gap sizes between
    catalog numbers, approximating where a record would physically sit if shelved
    by catalog number order with proportional spacing.
    """
    label = "SparseGappy"
    # Catalog numbers with deliberate large gaps to create uneven spacing
    # Gap structure: 1-10 (small gap), 10-50 (large gap), 50-55 (small), 55-100 (medium)
    catalogs = [
        "SG 001",
        "SG 010",
        "SG 050",
        "SG 055",
        "SG 056",
        "SG 057",
        "SG 099",
        "SG 100",
    ]
    cache = _build_cache(label, catalogs[0], catalogs[-1])
    snapshot = _build_snapshot(label, catalogs)

    # Extract numeric suffixes for gap-weighted position computation.
    # These are the "physical" positions based on catalog number spacing.
    nums = [1, 10, 50, 55, 56, 57, 99, 100]
    low, high = nums[0], nums[-1]
    span = high - low  # total span = 99

    # Pitfall F: truth is gap-weighted (physical shelf fraction), NOT idx/(k-1).
    # release_ids are 1-indexed per _build_snapshot.
    truth = {i + 1: (nums[i] - low) / span for i in range(len(nums))}
    return cache, snapshot, truth


def make_multi_prefix() -> tuple[BoundaryCache, CollectionSnapshot, dict[int, float]]:
    """Multi-prefix label: k=6 records with BLP and BST series (Blue Note style).

    Tests that parse_key correctly orders mixed-prefix catalog numbers and that
    §4.1 produces monotone positions. Planted truth uses idx/(k-1) because the
    physical shelving order follows parse_key ordering.
    """
    label = "MultiPrefix"
    # parse_key orders these as: BLP 100 < BLP 200 < BLP 300 < BST 84001 < BST 84002 < BST 84003
    catalogs = ["BLP 100", "BLP 200", "BLP 300", "BST 84001", "BST 84002", "BST 84003"]
    k = len(catalogs)
    cache = _build_cache(label, catalogs[0], catalogs[-1])
    snapshot = _build_snapshot(label, catalogs)

    # Pitfall F: truth is idx/(k-1) because physical order matches parse_key order
    truth = {i + 1: i / (k - 1) for i in range(k)}
    return cache, snapshot, truth


def make_singleton() -> tuple[BoundaryCache, CollectionSnapshot, dict[int, float]]:
    """Singleton label: k=1 record.

    Planted truth is 0.5 (midpoint of cube — best-guess for a single record).
    §4.1 returns start=0.0, end=1.0 (full-cube band, D-02) — correct behavior.
    """
    label = "Singleton"
    catalogs = ["SL 001"]
    cache = _build_cache(label, catalogs[0], catalogs[-1])
    snapshot = _build_snapshot(label, catalogs)

    # Singleton: physical truth is midpoint (0.5) — we don't know where in the cube it sits
    truth = {1: 0.5}
    return cache, snapshot, truth


# ── Registry ─────────────────────────────────────────────────────────────────


def all_shapes() -> dict[
    str, Callable[[], tuple[BoundaryCache, CollectionSnapshot, dict[int, float]]]
]:
    """Return the named factory registry.

    Used by:
      - tests/property/test_estimator_props.py (Hypothesis invariants)
      - scripts/run_all_algorithms.py (A/B harness)

    Returns:
        Dict mapping shape name → callable returning (cache, snapshot, truth).
    """
    return {
        "uniform_dense": make_uniform_dense,
        "sparse_gappy": make_sparse_gappy,
        "multi_prefix": make_multi_prefix,
        "singleton": make_singleton,
    }

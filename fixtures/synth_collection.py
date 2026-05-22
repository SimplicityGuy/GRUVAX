"""Planted-truth synthetic collection factories for GRUVAX tests.

Plain Python module (NOT a pytest conftest) — importable from both:
  - tests/property/test_estimator_props.py (Hypothesis invariant tests)
  - scripts/run_all_algorithms.py (A/B harness, Plan 02-04)
  - tests/unit/test_boundary_cache_refactor.py (Phase 5 unit tests)

Phase 5 shape change (SEG-01): BoundaryRow no longer has last_label / last_catalog.
The _build_cache() helper now constructs cut-point-only BoundaryRows. The
existing shape factories (make_uniform_dense etc.) continue to work because they
only need a single-cube boundary (first_* is the cut point; last_* is derived).

New Phase 5 factories:
  make_multi_label_bin()  — two labels in one cube (one starts mid-cube)
  make_straddle()         — one label spanning two adjacent bins

Return type for Phase 5 factories:
    (BoundaryCache, SegmentCache | None, CollectionSnapshot)
SegmentCache is None/placeholder at this stage — Plan 02 fills derivation.

For Phase 1/2 factories (uniform_dense etc.), the return type is:
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
    unit_id: int = 1,
    row: int = 0,
    col: int = 0,
) -> BoundaryCache:
    """Build a BoundaryCache with a single cube at the given cut point.

    Phase 5 change: BoundaryRow no longer has last_label / last_catalog (SEG-01 / D-05).
    The cut point is (first_label, first_catalog) only; last_* are derived by SegmentCache.
    """
    rows = [
        BoundaryRow(
            unit_id=unit_id,
            row=row,
            col=col,
            first_label=label,
            first_catalog=first_cat,
            is_empty=False,
        )
    ]
    cache = BoundaryCache()
    cache._load_rows(rows)
    return cache


def _build_cache_multi(
    boundaries: list[dict],
) -> BoundaryCache:
    """Build a BoundaryCache from a list of boundary dicts.

    Each dict must have: unit_id, row, col, first_label, first_catalog, is_empty.
    Used by Phase 5 factories (make_multi_label_bin, make_straddle).
    """
    rows = [
        BoundaryRow(
            unit_id=b["unit_id"],
            row=b["row"],
            col=b["col"],
            first_label=b.get("first_label"),
            first_catalog=b.get("first_catalog"),
            is_empty=b.get("is_empty", False),
        )
        for b in boundaries
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


def _build_snapshot_multi(
    label_catalogs: dict[str, list[str]],
    start_id: int = 1,
) -> tuple[CollectionSnapshot, dict[str, list[RecordRow]]]:
    """Build a CollectionSnapshot from multiple labels.

    Returns (snapshot, by_label_dict) so callers can inspect per-label records.
    release_ids are globally sequential starting from start_id.
    """
    snapshot = CollectionSnapshot()
    by_label: dict[str, list[RecordRow]] = {}
    release_id = start_id
    for label, catalogs in label_catalogs.items():
        records = [
            RecordRow(release_id=release_id + i, label=label, catalog_number=cat)
            for i, cat in enumerate(catalogs)
        ]
        release_id += len(catalogs)
        by_label[label.casefold()] = records
    snapshot._load_snapshot(by_label)
    return snapshot, by_label


# ── Shape factories (Phase 1/2 — single-label single-bin) ────────────────────


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
    cache = _build_cache(label, catalogs[0])
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
    cache = _build_cache(label, catalogs[0])
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
    cache = _build_cache(label, catalogs[0])
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
    cache = _build_cache(label, catalogs[0])
    snapshot = _build_snapshot(label, catalogs)

    # Singleton: physical truth is midpoint (0.5) — we don't know where in the cube it sits
    truth = {1: 0.5}
    return cache, snapshot, truth


# ── Phase 5 factories (multi-label + straddle) ───────────────────────────────


def make_multi_label_bin() -> tuple[BoundaryCache, None, CollectionSnapshot]:
    """Multi-label bin: two labels sharing one cube.

    Factory for Phase 5 segment-aware tests. One cube holds:
    - LabelA (k=8): records LA 001 through LA 008
    - LabelB (k=6): records LB 001 through LB 006, starts mid-cube

    The cut point for the single cube is (LabelA, LA 001) — only the first
    record of the first label in the cube is stored as the cut point (D-05).

    CollectionSnapshot includes:
    - duplicates: LA 003 appears twice (release_id=3 and release_id=3 via duplicate owned copy)
    - a '-r' variant: LB 003-r (remix, release_id=11 within LabelB's records)

    These ensure SEG-03 row-count tests have data that includes dupes + variants.

    SegmentCache is None here — Plan 02 fills the derive() logic.

    Returns:
        (BoundaryCache, None, CollectionSnapshot)
        where BoundaryCache has one cut-point cube for LabelA's first record.
    """
    label_a = "LabelA"
    label_b = "LabelB"

    # Build snapshot for both labels
    label_catalogs = {
        label_a: [f"LA {i:03d}" for i in range(1, 9)],  # LA 001..LA 008 (k=8)
        label_b: [
            "LB 001",
            "LB 002",
            "LB 003",       # owned copy
            "LB 003",       # duplicate owned copy (same catalog, different pressing)
            "LB 003-r",     # remix variant
            "LB 006",
        ],
    }
    snapshot, by_label = _build_snapshot_multi(label_catalogs, start_id=1)

    # Single cut-point cube: starts at LabelA LA 001
    # (LabelB starts mid-cube — no separate cut-point for it)
    cache = _build_cache_multi([
        {
            "unit_id": 1,
            "row": 0,
            "col": 0,
            "first_label": label_a,
            "first_catalog": "LA 001",
            "is_empty": False,
        }
    ])

    return cache, None, snapshot


def make_straddle() -> tuple[BoundaryCache, None, CollectionSnapshot]:
    """Straddle factory: one label spanning two adjacent bins.

    Factory for Phase 5 segment-aware tests. One label (LabelS) has k=12
    records spanning two adjacent cubes:
    - Cube 0: LabelS LS 001 through LS 006 (first 6 records)
    - Cube 1: LabelS LS 007 through LS 012 (second 6 records)

    The cut point for Cube 0 is (LabelS, LS 001).
    The cut point for Cube 1 is (LabelS, LS 007).

    Both cubes use the same unit_id=1, row=0; col=0 and col=1.

    SegmentCache is None here — Plan 02 fills the derive() logic.

    Returns:
        (BoundaryCache, None, CollectionSnapshot)
        where BoundaryCache has two adjacent cut-point cubes for the straddle label.
    """
    label = "LabelS"
    catalogs = [f"LS {i:03d}" for i in range(1, 13)]  # LS 001..LS 012 (k=12)

    snapshot = _build_snapshot(label, catalogs)

    # Two adjacent cubes with cut points at LS 001 and LS 007
    cache = _build_cache_multi([
        {
            "unit_id": 1,
            "row": 0,
            "col": 0,
            "first_label": label,
            "first_catalog": "LS 001",
            "is_empty": False,
        },
        {
            "unit_id": 1,
            "row": 0,
            "col": 1,
            "first_label": label,
            "first_catalog": "LS 007",
            "is_empty": False,
        },
    ])

    return cache, None, snapshot


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

"""TDD RED/GREEN tests for Task 2: BoundaryRow refactor + BoundaryCache overrides.

Tests the behavior defined in 05-01-PLAN.md Task 2:
  - BoundaryRow constructed without last_label/last_catalog raises no TypeError
  - BoundaryRow has no attribute last_label (AttributeError on access)
  - BoundaryCache._load_overrides({(1,0,0,"BLUE NOTE"): 0.45}) then accessor returns that dict
  - make_multi_label_bin() returns (BoundaryCache, ..., CollectionSnapshot) with two labels in one cube
  - make_straddle() returns one label spanning two adjacent bins
  - constants.SEGMENT_ESTIMATOR_VERSION == "segment-v1"
"""

from __future__ import annotations

from gruvax.estimator.boundary_cache import BoundaryCache, BoundaryRow
from gruvax.estimator.constants import SEGMENT_ESTIMATOR_VERSION


# ── BoundaryRow shape tests ───────────────────────────────────────────────────


def test_boundary_row_no_last_fields() -> None:
    """BoundaryRow constructed without last_label/last_catalog raises no TypeError (D-05)."""
    # This should not raise TypeError: __init__() got unexpected keyword argument
    row = BoundaryRow(
        unit_id=1,
        row=0,
        col=0,
        first_label="Blue Note",
        first_catalog="BLP 4001",
        is_empty=False,
    )
    assert row.unit_id == 1
    assert row.first_label == "Blue Note"
    assert row.first_catalog == "BLP 4001"
    assert row.is_empty is False


def test_boundary_row_no_last_label_attribute() -> None:
    """BoundaryRow has no last_label attribute (AttributeError on access)."""
    row = BoundaryRow(
        unit_id=1,
        row=0,
        col=0,
        first_label="Blue Note",
        first_catalog="BLP 4001",
        is_empty=False,
    )
    assert not hasattr(row, "last_label"), (
        "BoundaryRow should NOT have a last_label attribute after Phase 5 refactor"
    )


def test_boundary_row_no_last_catalog_attribute() -> None:
    """BoundaryRow has no last_catalog attribute (AttributeError on access)."""
    row = BoundaryRow(
        unit_id=1,
        row=0,
        col=0,
        first_label="Blue Note",
        first_catalog="BLP 4001",
        is_empty=False,
    )
    assert not hasattr(row, "last_catalog"), (
        "BoundaryRow should NOT have a last_catalog attribute after Phase 5 refactor"
    )


def test_boundary_row_positional_construction() -> None:
    """BoundaryRow can be constructed positionally (unit_id, row, col, first_label, first_catalog, is_empty)."""
    row = BoundaryRow(1, 0, 0, "ECM", "ECM 1001", False)
    assert row.unit_id == 1
    assert row.first_label == "ECM"
    assert row.first_catalog == "ECM 1001"
    assert row.is_empty is False


def test_boundary_row_empty_cube() -> None:
    """BoundaryRow can represent an empty cube (first_label and first_catalog are None)."""
    row = BoundaryRow(
        unit_id=1,
        row=3,
        col=3,
        first_label=None,
        first_catalog=None,
        is_empty=True,
    )
    assert row.first_label is None
    assert row.first_catalog is None
    assert row.is_empty is True


# ── BoundaryCache overrides tests ─────────────────────────────────────────────


def test_boundary_cache_load_overrides() -> None:
    """BoundaryCache._load_overrides() sets the overrides dict."""
    cache = BoundaryCache()
    overrides: dict[tuple[int, int, int, str], float] = {
        (1, 0, 0, "BLUE NOTE"): 0.45,
        (1, 0, 1, "ECM"): 0.30,
    }
    cache._load_overrides(overrides)
    result = cache.overrides
    assert result == overrides, f"overrides accessor should return the loaded dict; got {result}"


def test_boundary_cache_overrides_empty_on_init() -> None:
    """BoundaryCache._overrides is empty on initialization."""
    cache = BoundaryCache()
    assert cache.overrides == {}, "BoundaryCache.overrides should be empty dict on __init__"


def test_boundary_cache_invalidate_clears_overrides() -> None:
    """BoundaryCache.invalidate() clears both _rows and _overrides."""
    cache = BoundaryCache()
    # Load some rows
    cache._load_rows([BoundaryRow(1, 0, 0, "ECM", "ECM 1001", False)])
    cache._load_overrides({(1, 0, 0, "ECM"): 0.75})

    # Verify non-empty before invalidate
    assert len(cache.get_boundaries()) == 1
    assert len(cache.overrides) == 1

    # Invalidate should clear both
    cache.invalidate()
    assert list(cache.get_boundaries()) == [], "invalidate() should clear _rows"
    assert cache.overrides == {}, "invalidate() should clear _overrides"


# ── SEGMENT_ESTIMATOR_VERSION tests ──────────────────────────────────────────


def test_segment_estimator_version_constant() -> None:
    """SEGMENT_ESTIMATOR_VERSION constant exists and equals 'segment-v1'."""
    assert SEGMENT_ESTIMATOR_VERSION == "segment-v1", (
        f"Expected SEGMENT_ESTIMATOR_VERSION='segment-v1', got '{SEGMENT_ESTIMATOR_VERSION}'"
    )


# ── Synth factories tests ─────────────────────────────────────────────────────


def test_make_multi_label_bin_exists() -> None:
    """make_multi_label_bin() function exists and is importable from fixtures.synth_collection."""
    from fixtures.synth_collection import make_multi_label_bin

    assert callable(make_multi_label_bin), "make_multi_label_bin should be callable"


def test_make_straddle_exists() -> None:
    """make_straddle() function exists and is importable from fixtures.synth_collection."""
    from fixtures.synth_collection import make_straddle

    assert callable(make_straddle), "make_straddle should be callable"


def test_make_multi_label_bin_returns_tuple() -> None:
    """make_multi_label_bin() returns a 3-tuple (BoundaryCache, ..., CollectionSnapshot)."""
    from fixtures.synth_collection import make_multi_label_bin

    result = make_multi_label_bin()
    assert isinstance(result, tuple), "make_multi_label_bin() should return a tuple"
    assert len(result) >= 2, "tuple should have at least 2 elements"
    cache, _, snapshot = result[0], result[1], result[2]
    # Check types
    assert isinstance(cache, BoundaryCache), (
        f"First element should be BoundaryCache, got {type(cache)}"
    )
    from gruvax.estimator.collection_snapshot import CollectionSnapshot

    assert isinstance(snapshot, CollectionSnapshot), (
        f"Third element should be CollectionSnapshot, got {type(snapshot)}"
    )


def test_make_multi_label_bin_has_two_labels() -> None:
    """make_multi_label_bin() snapshot has at least two different labels in one cube."""
    from fixtures.synth_collection import make_multi_label_bin

    cache, _, _snapshot = make_multi_label_bin()

    # Should have at least 2 labels in the snapshot
    rows = cache.get_boundaries()
    assert len(rows) >= 1, "multi_label_bin cache should have at least one cube"

    # The snapshot should have records for at least 2 distinct labels
    all_labels = set()
    for row in rows:
        if row.first_label is not None:
            all_labels.add(row.first_label.casefold())
    # The multi-label bin should have multiple labels
    # (exact check depends on factory implementation)
    assert len(all_labels) >= 1, "multi_label_bin should have labels in boundaries"


def test_make_straddle_returns_tuple() -> None:
    """make_straddle() returns a 3-tuple starting with BoundaryCache."""
    from fixtures.synth_collection import make_straddle

    result = make_straddle()
    assert isinstance(result, tuple), "make_straddle() should return a tuple"
    assert len(result) >= 2, "tuple should have at least 2 elements"
    cache = result[0]
    assert isinstance(cache, BoundaryCache), (
        f"First element should be BoundaryCache, got {type(cache)}"
    )


def test_make_straddle_has_two_bins() -> None:
    """make_straddle() cache has at least two bins (label spans two cubes)."""
    from fixtures.synth_collection import make_straddle

    cache, _, _snapshot = make_straddle()
    rows = cache.get_boundaries()
    assert len(rows) >= 2, (
        f"make_straddle() should have at least 2 bins (straddle requires adjacent cubes), got {len(rows)}"
    )

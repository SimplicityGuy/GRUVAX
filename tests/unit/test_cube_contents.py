"""Unit tests for cube-contents sampling (CUBE-09).

Tests ``sample_records`` from ``gruvax.estimator.boundary_math``.
Authored RED in Plan 01 Task 2 (Wave-0 scaffold); goes GREEN when Task 3
implements ``boundary_math.py``.

Sampling contract (Pattern 8):
  - [] for empty input
  - Identity when len <= n
  - Exactly n records via index-stride, all members of the input

Analog: tests/unit/test_collection_snapshot.py (pure-function pattern).
"""

from __future__ import annotations

from gruvax.estimator.collection_snapshot import RecordRow


def _make_records(count: int, label: str = "Blue Note") -> list[RecordRow]:
    """Generate a list of count RecordRows for a label."""
    return [
        RecordRow(
            release_id=i,
            label=label,
            catalog_number=f"BLP {4000 + i}",
        )
        for i in range(1, count + 1)
    ]


def test_sample_empty() -> None:
    """sample_records([], n) returns [] for any n."""
    from gruvax.estimator.boundary_math import sample_records

    assert sample_records([], 7) == []
    assert sample_records([], 1) == []


def test_sample_identity_when_small() -> None:
    """sample_records returns the full list when len(records) <= n."""
    from gruvax.estimator.boundary_math import sample_records

    records = _make_records(5)
    result = sample_records(records, n=7)
    assert result == records, "sample_records must return the full list when len <= n"


def test_sample_size() -> None:
    """sample_records returns exactly n records when len > n (index-stride)."""
    from gruvax.estimator.boundary_math import sample_records

    records = _make_records(100)
    result = sample_records(records, n=7)
    assert len(result) == 7, f"Expected 7 samples, got {len(result)}"


def test_sample_subset() -> None:
    """All sampled records are members of the original input list."""
    from gruvax.estimator.boundary_math import sample_records

    records = _make_records(100)
    result = sample_records(records, n=7)
    records_set = {id(r) for r in records}
    for sampled in result:
        # Each sampled record must be an element of the original list (same object)
        assert id(sampled) in records_set, (
            f"Sampled record {sampled} is not a member of the original list"
        )


def test_sample_n_equals_len() -> None:
    """sample_records with n == len(records) returns all records."""
    from gruvax.estimator.boundary_math import sample_records

    records = _make_records(7)
    result = sample_records(records, n=7)
    assert len(result) == 7
    assert {r.release_id for r in result} == {r.release_id for r in records}


def test_sample_single() -> None:
    """sample_records with a single record returns that record."""
    from gruvax.estimator.boundary_math import sample_records

    records = _make_records(1)
    result = sample_records(records, n=7)
    assert result == records

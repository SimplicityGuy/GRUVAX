"""Property tests for YAML export round-trip identity (SC4).

Round-trip invariant: parse_yaml_boundaries(serialize_boundaries_yaml(entries))
yields the same entry set as the original entries (modulo ordering).

Uses Hypothesis for property-based coverage over synthetic CutPointEntry lists.
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from gruvax.io.boundary_yaml import CutPointEntry, parse_yaml_boundaries, serialize_boundaries_yaml


# ── Strategies ────────────────────────────────────────────────────────────────

label_str = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs")),
    min_size=1,
    max_size=40,
).filter(lambda s: s.strip() != "")

catalog_str = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    min_size=1,
    max_size=20,
).filter(lambda s: s.strip() != "")

override_dict = st.dictionaries(
    keys=label_str,
    values=st.floats(min_value=0.0001, max_value=1.0, allow_nan=False, allow_infinity=False),
    max_size=4,
)


def make_non_empty_entry(
    unit_id: int, row: int, col: int, label: str, catalog: str, overrides: dict
) -> CutPointEntry:
    return CutPointEntry(
        unit_id=unit_id,
        row=row,
        col=col,
        first_label=label,
        first_catalog=catalog,
        is_empty=False,
        overrides=overrides,
    )


def make_empty_entry(unit_id: int, row: int, col: int) -> CutPointEntry:
    return CutPointEntry(
        unit_id=unit_id,
        row=row,
        col=col,
        first_label=None,
        first_catalog=None,
        is_empty=True,
        overrides={},
    )


non_empty_entry_strategy = st.builds(
    make_non_empty_entry,
    unit_id=st.integers(min_value=1, max_value=10),
    row=st.integers(min_value=0, max_value=3),
    col=st.integers(min_value=0, max_value=3),
    label=label_str,
    catalog=catalog_str,
    overrides=override_dict,
)

empty_entry_strategy = st.builds(
    make_empty_entry,
    unit_id=st.integers(min_value=1, max_value=10),
    row=st.integers(min_value=0, max_value=3),
    col=st.integers(min_value=0, max_value=3),
)

entry_strategy = st.one_of(non_empty_entry_strategy, empty_entry_strategy)


def _key(e: CutPointEntry) -> tuple[int, int, int]:
    return (e.unit_id, e.row, e.col)


def _dedup(entries: list[CutPointEntry]) -> list[CutPointEntry]:
    """Keep only the last entry per (unit_id, row, col) key to avoid duplicates."""
    seen: dict[tuple[int, int, int], CutPointEntry] = {}
    for e in entries:
        seen[_key(e)] = e
    return list(seen.values())


# ── Property tests ────────────────────────────────────────────────────────────


@given(entries=st.lists(entry_strategy, min_size=0, max_size=10).map(_dedup))
@settings(max_examples=100)
def test_round_trip_identity(entries: list[CutPointEntry]) -> None:
    """serialize → parse yields the same entry set (SC4)."""
    yaml_str = serialize_boundaries_yaml(entries)
    reparsed = parse_yaml_boundaries(yaml_str)

    orig_sorted = sorted(entries, key=_key)
    reparsed_sorted = sorted(reparsed, key=_key)

    assert len(orig_sorted) == len(reparsed_sorted), (
        f"Entry count differs: {len(orig_sorted)} vs {len(reparsed_sorted)}"
    )
    for orig, rep in zip(orig_sorted, reparsed_sorted, strict=False):
        assert orig.unit_id == rep.unit_id
        assert orig.row == rep.row
        assert orig.col == rep.col
        assert orig.is_empty == rep.is_empty
        if not orig.is_empty:
            assert orig.first_label == rep.first_label
            assert orig.first_catalog == rep.first_catalog
            assert set(orig.overrides.keys()) == set(rep.overrides.keys())
            for k in orig.overrides:
                assert abs(orig.overrides[k] - rep.overrides[k]) < 1e-9


@given(
    label=label_str,
    catalog=catalog_str,
    overrides=st.fixed_dictionaries(
        {
            "Atlantic": st.just(0.45),
            "Blue Note": st.just(0.55),
        }
    ),
)
@settings(max_examples=20)
def test_overrides_survive_roundtrip(label: str, catalog: str, overrides: dict) -> None:
    """Overrides dict survives serialize → parse unchanged."""
    entry = CutPointEntry(
        unit_id=1,
        row=0,
        col=0,
        first_label=label,
        first_catalog=catalog,
        is_empty=False,
        overrides=overrides,
    )
    yaml_str = serialize_boundaries_yaml([entry])
    reparsed = parse_yaml_boundaries(yaml_str)
    assert len(reparsed) == 1
    rep = reparsed[0]
    assert rep.overrides == {"Atlantic": 0.45, "Blue Note": 0.55}

"""Unit tests for the POS-01 catalog-number parser/comparator.

Tests the golden cases described in PLAN.md §Task 1 <behavior>:
  - Numeric-aware ordering: parse_key("BLP 9") < parse_key("BLP 10")
  - Cosmetic stability: separator/case/whitespace variants compare equal
  - Multi-prefix discrimination: BLP vs BST
  - Placeholder/empty sort first
  - Multi-value catalogs use first part only
  - NFKC unicode normalization
  - catalog_in_range respects parse_key ordering
"""

from __future__ import annotations

import pytest

from gruvax.estimator.normalize import (
    catalog_in_range,
    compare_catalogs,
    normalize_catalog,
    parse_key,
)


# ── numeric-aware ordering ────────────────────────────────────────────────────


def test_numeric_aware_blp_9_lt_blp_10() -> None:
    """The classic lexical-sort failure: '9' > '10' as strings, but 9 < 10 numerically."""
    assert parse_key("BLP 9") < parse_key("BLP 10")


def test_numeric_aware_blp_9_lt_blp_100() -> None:
    assert parse_key("BLP 9") < parse_key("BLP 100")


def test_numeric_aware_pure_numeric() -> None:
    """Pure numeric catalog numbers must also sort numerically."""
    assert parse_key("9") < parse_key("10")
    assert parse_key("99") < parse_key("100")


def test_numeric_aware_large_numbers() -> None:
    assert parse_key("KC 32731") < parse_key("KC 32800")


# ── cosmetic stability ────────────────────────────────────────────────────────


def test_cosmetic_stability_space_vs_dash() -> None:
    assert parse_key("BLP 4195") == parse_key("blp-4195")


def test_cosmetic_stability_tab_separator() -> None:
    assert parse_key("BLP 4195") == parse_key("BLP\t4195")


def test_cosmetic_stability_no_separator() -> None:
    assert parse_key("blp4195") == parse_key("BLP 4195")


def test_cosmetic_stability_case_insensitive() -> None:
    assert parse_key("BLP 4195") == parse_key("blp 4195")


def test_cosmetic_stability_mixed_case() -> None:
    assert parse_key("ECM 1064") == parse_key("ecm-1064") == parse_key("ecm1064")


# ── multi-prefix discrimination ───────────────────────────────────────────────


def test_multi_prefix_blp_vs_bst() -> None:
    """Blue Note BLP and BST series must be distinct."""
    assert parse_key("BLP 4001") != parse_key("BST 4001")


def test_multi_prefix_ecm_vs_blp() -> None:
    assert parse_key("ECM 1001") != parse_key("BLP 1001")


def test_multi_prefix_ordering() -> None:
    """BLP < BST alphabetically after normalization."""
    assert parse_key("BLP 4001") < parse_key("BST 4001")


# ── placeholder and empty values sort FIRST ───────────────────────────────────


def test_placeholder_none_python() -> None:
    assert parse_key(None) <= parse_key("BLP 1")


def test_placeholder_empty_string() -> None:
    assert parse_key("") <= parse_key("BLP 1")


def test_placeholder_string_none() -> None:
    assert parse_key("none") <= parse_key("BLP 1")


def test_placeholder_na() -> None:
    assert parse_key("n/a") <= parse_key("BLP 1")


def test_placeholder_question_mark() -> None:
    assert parse_key("?") <= parse_key("BLP 1")


def test_placeholder_sorts_before_any_real_catalog() -> None:
    """All placeholder variants must sort strictly before real catalogs."""
    real_catalogs = ["BLP 4001", "ECM 1001", "1", "AAA"]
    for ph in (None, "", "none", "n/a", "n.a.", "?"):
        for real in real_catalogs:
            assert parse_key(ph) <= parse_key(real), (
                f"Expected parse_key({ph!r}) <= parse_key({real!r})"
            )


# ── multi-value: use first part only ─────────────────────────────────────────


def test_multivalue_uses_first_part() -> None:
    """'BLP-100, BST-200' should compare equal to 'BLP 100'."""
    assert parse_key("BLP-100, BST-200") == parse_key("BLP 100")


def test_multivalue_comma_split() -> None:
    assert parse_key("ECM 1064, ECM 1065") == parse_key("ECM 1064")


# ── NFKC normalization ────────────────────────────────────────────────────────


def test_nfkc_fullwidth_digits() -> None:
    """Full-width digits (U+FF10..U+FF19) should normalize to ASCII digits."""
    # U+FF14 = full-width '4', U+FF11 = '1', U+FF19 = '9', U+FF15 = '5'
    full_width = "BLP４１９５"
    assert parse_key(full_width) == parse_key("BLP 4195")


# ── normalize_catalog idempotency ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw",
    [
        "BLP 4195",
        "blp-4195",
        "ECM 1064",
        None,
        "",
        "none",
        "BLP-100, BST-200",
        "BLP\t4195",
    ],
)
def test_normalize_catalog_idempotent(raw: str | None) -> None:
    once = normalize_catalog(raw)
    twice = normalize_catalog(once)
    assert once == twice, f"normalize_catalog not idempotent for {raw!r}"


# ── compare_catalogs returns -1/0/1 ──────────────────────────────────────────


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ("BLP 4001", "BLP 4002", -1),
        ("BLP 4001", "BLP 4001", 0),
        ("BLP 4002", "BLP 4001", 1),
        ("BLP 9", "BLP 10", -1),   # numeric-aware
        ("BST 4001", "BLP 4001", 1),  # multi-prefix ordering
        (None, "BLP 1", -1),  # placeholder sorts first
        ("", "BLP 1", -1),
    ],
)
def test_compare_catalogs_values(a: str | None, b: str | None, expected: int) -> None:
    result = compare_catalogs(a, b)
    assert result == expected, f"compare_catalogs({a!r}, {b!r}) = {result}, want {expected}"


def test_compare_catalogs_antisymmetric() -> None:
    pairs = [
        ("BLP 4001", "BLP 4002"),
        ("BLP 9", "BLP 10"),
        ("ECM 1001", "BLP 4001"),
        (None, "BLP 1"),
    ]
    for a, b in pairs:
        r_ab = compare_catalogs(a, b)
        r_ba = compare_catalogs(b, a)
        assert r_ab == -r_ba or (r_ab == 0 and r_ba == 0), (
            f"Antisymmetry violated: compare_catalogs({a!r}, {b!r})={r_ab}, "
            f"compare_catalogs({b!r}, {a!r})={r_ba}"
        )


# ── catalog_in_range ──────────────────────────────────────────────────────────


def test_catalog_in_range_true() -> None:
    assert catalog_in_range("BLP 4010", "BLP 4001", "BLP 4020") is True


def test_catalog_in_range_boundary_inclusive_lower() -> None:
    assert catalog_in_range("BLP 4001", "BLP 4001", "BLP 4020") is True


def test_catalog_in_range_boundary_inclusive_upper() -> None:
    assert catalog_in_range("BLP 4020", "BLP 4001", "BLP 4020") is True


def test_catalog_in_range_false_below() -> None:
    assert catalog_in_range("BLP 3999", "BLP 4001", "BLP 4020") is False


def test_catalog_in_range_false_above() -> None:
    assert catalog_in_range("BLP 4021", "BLP 4001", "BLP 4020") is False


def test_catalog_in_range_numeric_edge() -> None:
    """The critical test: BLP 9 must be BELOW BLP 10 — proving numeric awareness."""
    # BLP 9 should be in range [BLP 1, BLP 9] but not in [BLP 10, BLP 20]
    assert catalog_in_range("BLP 9", "BLP 1", "BLP 9") is True
    assert catalog_in_range("BLP 9", "BLP 10", "BLP 20") is False


def test_catalog_in_range_separator_variants() -> None:
    """Cosmetic variants of the same catalog# must compare equal for range membership."""
    assert catalog_in_range("blp-4010", "BLP 4001", "BLP 4020") is True
    assert catalog_in_range("BLP4010", "BLP 4001", "BLP 4020") is True

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

import itertools

import pytest

from gruvax.estimator.normalize import (
    catalog_in_range,
    compare_catalogs,
    label_sort_key,
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
    """Full-width digits (U+FF10..U+FF19) should normalize to ASCII digits via NFKC."""
    # Build using chr() to avoid RUF001 ambiguous-character linter warning.
    # U+FF14='4', U+FF11='1', U+FF19='9', U+FF15='5' (full-width forms)
    full_width = "BLP" + chr(0xFF14) + chr(0xFF11) + chr(0xFF19) + chr(0xFF15)
    assert parse_key(full_width) == parse_key("BLP 4195")


def test_nfkc_fullwidth_letters_and_hyphen() -> None:
    """ADR-0001 witness: a full-width "BLP-4195" folds to the same key as 'BLP 4195'.

    Exercises normalize_catalog / parse_key across full-width LETTERS (U+FF22 'B',
    U+FF2C 'L', U+FF30 'P'), a full-width hyphen-minus (U+FF0D, separator), and
    full-width DIGITS (U+FF14/FF11/FF19/FF15) — the shelved-vs-searchable identity
    gap the authority closes. Built via chr() so the source stays pure-ASCII.
    """
    # chr() avoids RUF001/RUF002 ambiguous-character linter warnings on full-width forms.
    full_width = (
        chr(0xFF22)  # 'B'
        + chr(0xFF2C)  # 'L'
        + chr(0xFF30)  # 'P'
        + chr(0xFF0D)  # '-' full-width hyphen-minus
        + chr(0xFF14)  # '4'
        + chr(0xFF11)  # '1'
        + chr(0xFF19)  # '9'
        + chr(0xFF15)  # '5'
    )
    assert normalize_catalog(full_width) == normalize_catalog("BLP 4195")
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
        ("BLP 9", "BLP 10", -1),  # numeric-aware
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


# ── label_sort_key (ADR-0001 label-ordering authority) ────────────────────────

# The ADR-0001 witness list, in its authoritative pyuca (UCA) order.
_WITNESS_LABELS_SORTED: list[str] = [
    "4AD",
    "A&M",
    "ABC",
    "Ace",
    "Blue Note",
    "Bluebird",
    "Éditions EG",
    "ZZ Top Records",
]


def test_label_sort_key_orders_adr_witness_list() -> None:
    """The ADR-0001 witness labels sort into their documented deterministic order.

    This is the property that makes the admin picker and the estimator cut-key
    order agree: digits first (4AD), punctuation/space significant and below
    letters (A&M < ABC, Blue Note < Bluebird), accents fold to base primary
    weight (Éditions EG under 'E').
    """
    # A fixed, deliberately out-of-order permutation of the witness list.
    scrambled = [
        "Éditions EG",
        "ABC",
        "4AD",
        "ZZ Top Records",
        "Ace",
        "Bluebird",
        "A&M",
        "Blue Note",
    ]
    assert sorted(scrambled) != _WITNESS_LABELS_SORTED  # naive str sort disagrees
    assert sorted(scrambled, key=label_sort_key) == _WITNESS_LABELS_SORTED


def test_label_sort_key_deterministic() -> None:
    """label_sort_key is a pure function of its input — same input, identical key."""
    for label in _WITNESS_LABELS_SORTED:
        assert label_sort_key(label) == label_sort_key(label)


def test_label_sort_key_witness_pairs_strictly_ordered() -> None:
    """Every adjacent witness pair is strictly ordered (total order, no ties)."""
    for lo, hi in itertools.pairwise(_WITNESS_LABELS_SORTED):
        assert label_sort_key(lo) < label_sort_key(hi), f"{lo!r} !< {hi!r}"


def test_label_sort_key_case_insensitive() -> None:
    """Casefold means case-variant labels collate equal (one bin, not two)."""
    assert label_sort_key("Blue Note") == label_sort_key("BLUE NOTE")
    assert label_sort_key("blue note") == label_sort_key("Blue Note")


def test_label_sort_key_none_and_empty_sort_first() -> None:
    """None / empty labels produce the minimal key and sort before any real label."""
    assert label_sort_key(None) == label_sort_key("")
    assert label_sort_key(None) <= label_sort_key("4AD")


def test_label_sort_key_punctuation_below_letters() -> None:
    """A&M sorts before ABC: '&' is significant and weighted below letters (UCA)."""
    assert label_sort_key("A&M") < label_sort_key("ABC")

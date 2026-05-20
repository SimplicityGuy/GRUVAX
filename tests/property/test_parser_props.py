"""Hypothesis property tests for the POS-01 catalog-number parser.

Properties (per RESEARCH.md §Pattern 2 and INTERPOLATION.md §3.4):
  1. Total order: compare_catalogs(a, b) ∈ {-1, 0, 1} and antisymmetric
  2. Idempotent: normalize_catalog(normalize_catalog(s)) == normalize_catalog(s)
  3. Numeric-aware monotonicity: for same prefix, higher numeric suffix → greater key
  4. Cosmetic stability: separator/case variants of the same catalog compare equal
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from gruvax.estimator.normalize import (
    catalog_in_range,
    compare_catalogs,
    normalize_catalog,
    parse_key,
)

# ── total order ───────────────────────────────────────────────────────────────


@given(a=st.text(), b=st.text())
@settings(max_examples=500)
def test_compare_catalogs_returns_valid_value(a: str, b: str) -> None:
    """compare_catalogs must always return -1, 0, or 1."""
    result = compare_catalogs(a, b)
    assert result in (-1, 0, 1), f"compare_catalogs({a!r}, {b!r}) = {result!r}"


@given(a=st.text(), b=st.text())
@settings(max_examples=500)
def test_compare_catalogs_antisymmetric(a: str, b: str) -> None:
    """compare_catalogs(a, b) == -compare_catalogs(b, a) (antisymmetry / total order)."""
    r_ab = compare_catalogs(a, b)
    r_ba = compare_catalogs(b, a)
    assert r_ab == -r_ba or (r_ab == 0 and r_ba == 0), (
        f"Antisymmetry violated: compare_catalogs({a!r},{b!r})={r_ab}, "
        f"compare_catalogs({b!r},{a!r})={r_ba}"
    )


@given(a=st.text(), b=st.text(), c=st.text())
@settings(max_examples=300)
def test_compare_catalogs_transitive(a: str, b: str, c: str) -> None:
    """Transitivity: if a <= b and b <= c, then a <= c."""
    ab = compare_catalogs(a, b)
    bc = compare_catalogs(b, c)
    ac = compare_catalogs(a, c)
    if ab <= 0 and bc <= 0:
        assert ac <= 0, (
            f"Transitivity violated: {a!r} <= {b!r} <= {c!r} but "
            f"compare_catalogs({a!r},{c!r})={ac}"
        )


# ── idempotent normalization ──────────────────────────────────────────────────


@given(s=st.text())
@settings(max_examples=500)
def test_idempotent_normalize(s: str) -> None:
    """normalize_catalog must be idempotent."""
    once = normalize_catalog(s)
    twice = normalize_catalog(once)
    assert once == twice, f"normalize_catalog not idempotent for {s!r}"


@given(s=st.text())
@settings(max_examples=500)
def test_parse_key_stable_on_normalized(s: str) -> None:
    """parse_key(normalize_catalog(s)) == parse_key(s): keys are stable post-normalize."""
    assert parse_key(s) == parse_key(normalize_catalog(s)), (
        f"parse_key not stable: parse_key({s!r}) != parse_key(normalize_catalog({s!r}))"
    )


# ── numeric-aware monotonicity ────────────────────────────────────────────────


@given(
    prefix=st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", min_size=1, max_size=5),
    n=st.integers(min_value=0, max_value=9999),
)
@settings(max_examples=300)
def test_numeric_monotone_with_prefix(prefix: str, n: int) -> None:
    """For same ASCII alpha prefix, parse_key(prefix+N) <= parse_key(prefix+(N+1))."""
    a = f"{prefix}{n}"
    b = f"{prefix}{n + 1}"
    assert parse_key(a) <= parse_key(b), (
        f"Numeric monotonicity violated: parse_key({a!r}) > parse_key({b!r})"
    )


@given(n=st.integers(min_value=0, max_value=99999))
@settings(max_examples=300)
def test_pure_numeric_monotone(n: int) -> None:
    """Pure numeric catalogs: parse_key(str(n)) <= parse_key(str(n+1))."""
    a = str(n)
    b = str(n + 1)
    assert parse_key(a) <= parse_key(b), (
        f"Pure numeric monotonicity violated: parse_key({a!r}) > parse_key({b!r})"
    )


# ── cosmetic stability: separator variants ────────────────────────────────────


@given(
    prefix=st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", min_size=1, max_size=5),
    n=st.integers(min_value=1, max_value=9999),
    sep=st.sampled_from([" ", "-", "_", ".", "/", ""]),
)
@settings(max_examples=300)
def test_cosmetic_stability_separators(prefix: str, n: int, sep: str) -> None:
    """Changing separator between prefix and digits must not change parse_key.

    Restricted to ASCII alpha prefixes because the tokenizer (_TOKEN regex) only
    recognizes ASCII letters; non-ASCII chars in the prefix would be silently
    discarded, making case comparison undefined.
    """
    base = f"{prefix} {n}"  # canonical form with space
    variant = f"{prefix}{sep}{n}"
    assert parse_key(base) == parse_key(variant), (
        f"Cosmetic stability violated: parse_key({base!r}) != parse_key({variant!r})"
    )


@given(
    prefix=st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", min_size=1, max_size=5),
    n=st.integers(min_value=1, max_value=9999),
)
@settings(max_examples=300)
def test_cosmetic_stability_case(prefix: str, n: int) -> None:
    """Case variants of same catalog must produce equal parse_key.

    Restricted to ASCII alpha because the tokenizer matches [A-Za-z]; non-ASCII
    letters would be discarded differently by upper/lower, making case stability
    undefined for those characters.
    """
    lower = f"{prefix.lower()} {n}"
    upper = f"{prefix.upper()} {n}"
    assert parse_key(lower) == parse_key(upper), (
        f"Case stability violated: parse_key({lower!r}) != parse_key({upper!r})"
    )


# ── digit cap (DoS protection, T-01-05) ─────────────────────────────────────


@given(
    n_digits=st.integers(min_value=13, max_value=30),
    digit=st.integers(min_value=0, max_value=9),
)
@settings(max_examples=100)
def test_digit_cap_no_exception(n_digits: int, digit: int) -> None:
    """parse_key must not raise for any length digit run (barcode outlier protection)."""
    catalog = str(digit) * n_digits
    try:
        result = parse_key(catalog)
        assert isinstance(result, tuple)
    except Exception as exc:
        raise AssertionError(
            f"parse_key raised on digit-run of length {n_digits}: {exc}"
        ) from exc


# ── catalog_in_range consistency ──────────────────────────────────────────────


@given(a=st.text(), b=st.text())
@settings(max_examples=300)
def test_catalog_in_range_self_contained(a: str, b: str) -> None:
    """catalog_in_range(a, a, b): always true when first==last==catalog."""
    assert catalog_in_range(a, a, a) is True, (
        f"catalog_in_range({a!r}, {a!r}, {a!r}) should be True"
    )

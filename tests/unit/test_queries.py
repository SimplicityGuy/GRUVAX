"""Unit tests for queries.py — pure-function and graceful-degrade tests.

Wave-0 tests (no live DB required):
  - test_is_catalog_query_truth_table: parametrized truth table for D-12
  - test_did_you_mean_graceful_degrade: mock UndefinedFunction → None (Pitfall E)
  - test_did_you_mean_returns_top_match: mock cursor returning match → term returned

These tests use minimal async fakes (no real Postgres) so they run locally
in CI without a lux DB connection.
"""

from __future__ import annotations

import psycopg.errors
import pytest

from gruvax.db.queries import (
    DID_YOU_MEAN_THRESHOLD,
    did_you_mean_query,
    get_catalogs_for_label,
    get_distinct_labels,
    is_catalog_query,
)
from gruvax.estimator.normalize import label_sort_key, parse_key


# ── is_catalog_query truth table (D-12) ───────────────────────────────────────


@pytest.mark.parametrize(
    "q,expected",
    [
        # Leading digit — True
        ("4195", True),
        ("19BOX019", True),
        ("1SHOT-002", True),
        # Prefix + digits — True
        ("BLP 41", True),
        ("ECM 10", True),
        ("blp4195", True),
        # Text-only queries — False
        ("Miles Davis", False),
        ("Coltrane", False),
        ("", False),
        ("Blue Note", False),
        # Edge cases
        ("A", False),  # prefix without digits
        ("abc xyz", False),  # no digits at all
        (" 42", True),  # leading space + digit (strip normalizes)
    ],
)
def test_is_catalog_query_truth_table(q: str, expected: bool) -> None:
    """is_catalog_query must correctly classify catalog-like vs text queries (D-12)."""
    assert is_catalog_query(q) is expected, (
        f"is_catalog_query({q!r}) expected {expected}, got {not expected}"
    )


# ── Minimal async fake pool helpers ───────────────────────────────────────────


def _make_fake_pool_raising(exc: Exception) -> object:
    """Return a fake pool whose cursor.execute raises *exc*."""

    class FakeCursor:
        async def execute(self, sql: str, params: tuple) -> None:
            raise exc

        async def fetchone(self) -> None:
            return None

        async def __aenter__(self) -> FakeCursor:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

    class FakeConn:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

        async def __aenter__(self) -> FakeConn:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

    class FakePool:
        def connection(self) -> FakeConn:
            return FakeConn()

    return FakePool()


def _make_fake_pool_returning(rows: list[tuple]) -> object:
    """Return a fake pool whose cursor.fetchone returns *rows[0]* (if any)."""

    class FakeCursor:
        async def execute(self, sql: str, params: tuple) -> None:
            pass

        async def fetchone(self) -> tuple | None:
            return rows[0] if rows else None

        async def __aenter__(self) -> FakeCursor:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

    class FakeConn:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

        async def __aenter__(self) -> FakeConn:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

    class FakePool:
        def connection(self) -> FakeConn:
            return FakeConn()

    return FakePool()


# ── did_you_mean_query graceful degrade (Pitfall E) ──────────────────────────


@pytest.mark.asyncio
async def test_did_you_mean_graceful_degrade() -> None:
    """When pg_trgm is absent (UndefinedFunction), did_you_mean_query returns None.

    This test verifies Pitfall E: the similarity() function is undefined when
    pg_trgm has not been installed.  The search still returns 200 with
    did_you_mean=null.
    """
    exc = psycopg.errors.UndefinedFunction()
    fake_pool = _make_fake_pool_raising(exc)
    result = await did_you_mean_query(
        fake_pool, "Miles Daviss", profile_id="00000000-0000-0000-0000-000000000001"
    )  # type: ignore[arg-type]
    assert result is None, f"Expected None when UndefinedFunction raised, got {result!r}"


@pytest.mark.asyncio
async def test_did_you_mean_returns_top_match() -> None:
    """When pg_trgm is available and a row exceeds threshold, return the term.

    The fake pool returns one (term, sim) row above DID_YOU_MEAN_THRESHOLD.
    did_you_mean_query should return the term string.
    """
    # Fake pool returns ("Blue Note", 0.6) — well above 0.35 threshold.
    term = "Blue Note"
    sim = DID_YOU_MEAN_THRESHOLD + 0.25  # clearly above threshold
    fake_pool = _make_fake_pool_returning([(term, sim)])
    result = await did_you_mean_query(
        fake_pool, "Bleu Note", profile_id="00000000-0000-0000-0000-000000000001"
    )  # type: ignore[arg-type]
    assert result == term, f"Expected {term!r}, got {result!r}"


@pytest.mark.asyncio
async def test_did_you_mean_returns_none_when_no_rows() -> None:
    """When no terms exceed the threshold, did_you_mean_query returns None."""
    fake_pool = _make_fake_pool_returning([])
    result = await did_you_mean_query(
        fake_pool, "zzznomatch", profile_id="00000000-0000-0000-0000-000000000001"
    )  # type: ignore[arg-type]
    assert result is None, f"Expected None when no rows returned, got {result!r}"


# ── Fake pool returning a full result set (fetchall) ──────────────────────────


def _make_fake_pool_fetchall(rows: list[tuple]) -> object:
    """Return a fake pool whose cursor.fetchall returns *rows* verbatim."""

    class FakeCursor:
        async def execute(self, sql: str, params: tuple) -> None:
            pass

        async def fetchall(self) -> list[tuple]:
            return list(rows)

        async def __aenter__(self) -> FakeCursor:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

    class FakeConn:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

        async def __aenter__(self) -> FakeConn:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

    class FakePool:
        def connection(self) -> FakeConn:
            return FakeConn()

    return FakePool()


# ── gruvax-icc5: picker ordering is the pyuca authority, not SQL glibc ─────────


@pytest.mark.asyncio
async def test_get_distinct_labels_sorted_by_pyuca_not_sql_order() -> None:
    """get_distinct_labels re-sorts in Python by label_sort_key (ADR-0001).

    The DB rows arrive in the SQL ``ORDER BY label`` (glibc) order — which is not
    load-bearing. The helper must return them in the pyuca authority order so the
    admin label picker agrees with the estimator's cut-key order (gruvax-icc5).
    The witness set includes the accent case ``Éditions EG``, which glibc/codepoint
    order sorts after ``Z`` but pyuca sorts mid-alphabet under ``E``.
    """
    # Rows as the DB might hand them back — deliberately NOT in pyuca order.
    db_rows = [
        ("ZZ Top Records",),
        ("Éditions EG",),
        ("Ace",),
        ("A&M",),
        ("Blue Note",),
        ("Bluebird",),
        ("4AD",),
        ("ABC",),
    ]
    fake_pool = _make_fake_pool_fetchall(db_rows)
    result = await get_distinct_labels(fake_pool)  # type: ignore[arg-type]

    expected = sorted((r[0] for r in db_rows), key=label_sort_key)
    assert result == expected
    # Concrete authority order (pyuca): punctuation < letters, space < letters,
    # accents fold to base — Éditions EG lands mid-alphabet, ZZ Top last.
    assert result == [
        "4AD",
        "A&M",
        "ABC",
        "Ace",
        "Blue Note",
        "Bluebird",
        "Éditions EG",
        "ZZ Top Records",
    ]
    # Éditions EG must sort BEFORE ZZ Top (mid-alphabet), not after Z.
    assert result.index("Éditions EG") < result.index("ZZ Top Records")


@pytest.mark.asyncio
async def test_get_catalogs_for_label_sorted_by_parse_key_numeric_aware() -> None:
    """get_catalogs_for_label re-sorts by parse_key — numeric-aware, not lexical.

    The catalog picker must present catalogs in the same within-label order the
    estimator ranks records (ADR-0001), so ``BLP 9`` precedes ``BLP 10`` (numeric)
    rather than the SQL lexical order where ``BLP 10`` < ``BLP 9``.
    """
    # DB returns lexical SQL order (BLP 10 before BLP 9).
    db_rows = [
        (1, "BLP 10"),
        (2, "BLP 100"),
        (3, "BLP 9"),
    ]
    fake_pool = _make_fake_pool_fetchall(db_rows)
    result = await get_catalogs_for_label(fake_pool, "Blue Note")  # type: ignore[arg-type]

    cats = [r["catalog_number"] for r in result]
    assert cats == ["BLP 9", "BLP 10", "BLP 100"]
    assert cats == sorted(cats, key=parse_key)

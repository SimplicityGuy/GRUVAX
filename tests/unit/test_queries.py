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

from gruvax.db.queries import DID_YOU_MEAN_THRESHOLD, did_you_mean_query, is_catalog_query


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

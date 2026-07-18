"""Unit tests for the gruvax-nrx2 boot-time already-populated guard.

docker-entrypoint.sh ran `python -m gruvax.db.seed_boundaries` on every
container start, gated ONLY on the fixture file existing — no GRUVAX_ENV
check, no already-populated guard. Its ON CONFLICT DO UPDATE upsert would
therefore silently revert admin cut-point edits on the default profile back
to the synthetic dev fixture on every restart, in production too.

The fix keeps `load_boundaries` an unconditional upsert (integration tests
rely on it to force-restore canonical fixture state after a mutating test)
and adds a NEW boot-time entry point, `seed_boundaries_guarded`, that skips
seeding entirely once the default profile already has any cube_boundaries
rows. `main()` (the CLI entry docker-entrypoint.sh invokes) now calls the
guarded entry point instead of `load_boundaries` directly.

These tests exercise `_is_already_populated` and `seed_boundaries_guarded`
against fake psycopg-shaped async connection/cursor/pool objects — no real
database required.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from gruvax.db import seed_boundaries as sb


# ── Fake psycopg-shaped async connection / pool ──────────────────────────────


class _FakeCursor:
    """Minimal async cursor stub: records the executed SQL and returns a fixed row."""

    def __init__(self, count: int) -> None:
        self._count = count
        self.executed_sql: str | None = None

    async def __aenter__(self) -> _FakeCursor:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        self.executed_sql = sql

    async def fetchone(self) -> tuple[int]:
        return (self._count,)


class _FakeConn:
    """Minimal async connection stub exposing only `.cursor()`.

    Tracks the most recently created cursor so tests can inspect the SQL a
    call actually issued.
    """

    def __init__(self, count: int) -> None:
        self._count = count
        self.last_cursor: _FakeCursor | None = None

    def cursor(self) -> _FakeCursor:
        cur = _FakeCursor(self._count)
        self.last_cursor = cur
        return cur


class _FakeConnCtx:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeConn:
        return self._conn

    async def __aexit__(self, *exc_info: object) -> None:
        return None


class _FakePool:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    def connection(self) -> _FakeConnCtx:
        return _FakeConnCtx(self._conn)


class _FakePoolCtx:
    def __init__(self, pool: _FakePool) -> None:
        self._pool = pool

    async def __aenter__(self) -> _FakePool:
        return self._pool

    async def __aexit__(self, *exc_info: object) -> None:
        return None


# ── _is_already_populated ─────────────────────────────────────────────────────


async def test_is_already_populated_false_when_zero_rows() -> None:
    """A fresh default profile (COUNT=0) is reported as NOT already populated."""
    conn = _FakeConn(count=0)
    assert await sb._is_already_populated(conn) is False


async def test_is_already_populated_true_when_rows_exist() -> None:
    """A default profile with existing rows (e.g. admin cut-point edits) is
    reported as already populated."""
    conn = _FakeConn(count=7)
    assert await sb._is_already_populated(conn) is True


async def test_is_already_populated_scopes_query_to_default_profile() -> None:
    """The guard's COUNT query is scoped to gruvax.cube_boundaries for the
    default profile — it must not count rows across every profile."""
    conn = _FakeConn(count=0)
    await sb._is_already_populated(conn)

    assert conn.last_cursor is not None
    executed_sql = conn.last_cursor.executed_sql
    assert executed_sql is not None
    assert "gruvax.cube_boundaries" in executed_sql
    assert "profile_id" in executed_sql


# ── seed_boundaries_guarded ────────────────────────────────────────────────────


async def test_seed_boundaries_guarded_skips_when_already_populated() -> None:
    """gruvax-nrx2: once the default profile has any cube_boundaries rows,
    the boot guard must NOT call load_boundaries — this is exactly what stops
    a container restart from reverting admin cut-point edits back to the
    synthetic dev fixture."""
    fake_pool = _FakePool(_FakeConn(count=1))
    with (
        patch.object(sb, "get_pool_context", return_value=_FakePoolCtx(fake_pool)),
        patch.object(sb, "load_boundaries", new_callable=AsyncMock) as mock_load,
    ):
        await sb.seed_boundaries_guarded(Path("fixtures/boundaries.yaml"))
    mock_load.assert_not_called()


async def test_seed_boundaries_guarded_seeds_when_empty() -> None:
    """On a fresh default profile (COUNT=0, e.g. a virgin database), the boot
    guard proceeds to seed exactly as before."""
    fake_pool = _FakePool(_FakeConn(count=0))
    yaml_path = Path("fixtures/boundaries.yaml")
    with (
        patch.object(sb, "get_pool_context", return_value=_FakePoolCtx(fake_pool)),
        patch.object(sb, "load_boundaries", new_callable=AsyncMock) as mock_load,
    ):
        await sb.seed_boundaries_guarded(yaml_path)
    mock_load.assert_awaited_once_with(yaml_path)


@pytest.mark.parametrize("count", [0, 1, 42])
async def test_seed_boundaries_guarded_calls_load_iff_empty(count: int) -> None:
    """Parametrized boundary check: load_boundaries runs exactly when COUNT==0,
    never otherwise — the guard has no partial/threshold behavior."""
    fake_pool = _FakePool(_FakeConn(count=count))
    with (
        patch.object(sb, "get_pool_context", return_value=_FakePoolCtx(fake_pool)),
        patch.object(sb, "load_boundaries", new_callable=AsyncMock) as mock_load,
    ):
        await sb.seed_boundaries_guarded(Path("fixtures/boundaries.yaml"))
    if count == 0:
        mock_load.assert_awaited_once()
    else:
        mock_load.assert_not_called()

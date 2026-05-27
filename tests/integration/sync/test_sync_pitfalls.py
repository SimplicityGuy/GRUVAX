"""Integration tests for Pitfalls 1 + 8 — Plan 01-03 Task 2.

Pitfall 1 (RESEARCH.md): stale 'in_progress' state should produce an
operator-actionable SyncInProgress message, not opaque "another sync
already running" spam.

Pitfall 8 (RESEARCH.md): the migration-seeded sentinel-bytea PAT
placeholder (`'\\x'::bytea` + revoked=TRUE) must short-circuit BEFORE
sync_profile constructs DiscogsographyClient — no noisy 401 hitting
the upstream API.
"""

from __future__ import annotations

import os
import types
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from gruvax.discogsography.errors import PATRejected, SyncInProgress
from gruvax.settings import settings
from gruvax.sync import profile_sync
from gruvax.sync.pat_crypto import encrypt_pat
from gruvax.sync.profile_sync import _lock_key, sync_profile


if TYPE_CHECKING:
    from collections.abc import AsyncIterator


DEFAULT_UUID = "00000000-0000-0000-0000-000000000001"
TEST_PAT = "dscg_test_pat_LEAK_DETECTOR_secret_aaa"


# ── fixtures + helpers ───────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _ensure_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    if not os.environ.get("GRUVAX_SECRET_KEY"):
        from cryptography.fernet import Fernet

        monkeypatch.setenv("GRUVAX_SECRET_KEY", Fernet.generate_key().decode())


def _make_app_state(db_pool) -> types.SimpleNamespace:  # type: ignore[no-untyped-def]
    snapshot = AsyncMock()
    snapshot.invalidate = lambda: None
    boundary = AsyncMock()
    segment = AsyncMock()
    segment.derive = lambda *a, **kw: None
    boundary.overrides = {}
    return types.SimpleNamespace(
        db_pool=db_pool,
        collection_snapshot=snapshot,
        boundary_cache=boundary,
        segment_cache=segment,
    )


@pytest_asyncio.fixture(loop_scope="session")
async def _reset_after(db_pool) -> AsyncIterator[None]:  # type: ignore[no-untyped-def]
    """Always release the advisory lock + restore a clean row after the test.

    Pitfall-1 / -8 tests deliberately put the row into bad states; the
    teardown restores a known-good shape so the next test in the suite
    doesn't inherit corruption.
    """
    yield
    # Best-effort: release any leaked advisory lock + reset the row.
    async with db_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT pg_advisory_unlock_all()")
        await conn.execute(
            "UPDATE gruvax.profiles "
            "SET app_token_encrypted = %s, app_token_revoked = FALSE, "
            "    last_sync_status = NULL, last_sync_error = NULL, "
            "    last_sync_at = NULL "
            "WHERE id = %s::uuid",
            (encrypt_pat(TEST_PAT), DEFAULT_UUID),
        )
        await conn.commit()


# ── tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_stale_in_progress_surfaces_actionable_message(  # type: ignore[no-untyped-def]
    db_pool, _reset_after
) -> None:
    """Test 5: stale lock detection — clear message mentioning 'stale'.

    Setup: another session holds the advisory lock AND the profile row is
    marked 'in_progress' with last_sync_at 10 minutes ago. sync_profile
    must raise SyncInProgress with a 'stale'-mentioning message.
    """
    import psycopg

    # 1. Set the stale state on the profile row.
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.profiles SET "
            "    last_sync_status = 'in_progress', "
            "    last_sync_at = now() - INTERVAL '10 minutes', "
            "    app_token_encrypted = %s, "
            "    app_token_revoked = FALSE "
            "WHERE id = %s::uuid",
            (encrypt_pat(TEST_PAT), DEFAULT_UUID),
        )
        await conn.commit()

    # 2. Hold the advisory lock on a separate connection so the next
    #    sync_profile cannot acquire it.
    lock_key = _lock_key(DEFAULT_UUID)
    conninfo = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    holder = await psycopg.AsyncConnection.connect(conninfo)
    try:
        async with holder.cursor() as cur:
            await cur.execute("SELECT pg_try_advisory_lock(%s)", (lock_key,))
            assert (await cur.fetchone())[0] is True

        # 3. sync_profile must raise SyncInProgress with a stale-mentioning msg.
        with pytest.raises(SyncInProgress) as exc_info:
            await sync_profile(DEFAULT_UUID, _make_app_state(db_pool))
        assert "stale" in str(exc_info.value).lower()
    finally:
        async with holder.cursor() as cur:
            await cur.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))
        await holder.close()


@pytest.mark.asyncio(loop_scope="session")
async def test_sentinel_pat_short_circuits_without_http(  # type: ignore[no-untyped-def]
    db_pool, _reset_after, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 6: empty-bytes placeholder + revoked=TRUE → PATRejected, no HTTP.

    Setup: restore the migration-seeded shape — `'\\x'::bytea` + revoked=TRUE.
    sync_profile must raise PATRejected without ever calling _make_client.
    """
    # 1. Restore the migration-seed shape.
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.profiles SET "
            "    app_token_encrypted = '\\x'::bytea, "
            "    app_token_revoked = TRUE, "
            "    last_sync_status = NULL, "
            "    last_sync_error = NULL "
            "WHERE id = %s::uuid",
            (DEFAULT_UUID,),
        )
        await conn.commit()

    # 2. Sentinel-detector: if _make_client is ever called, fail.
    call_count: list[int] = []

    def _fail_if_called(base_url: str, pat: str):  # type: ignore[no-untyped-def]
        call_count.append(1)
        raise AssertionError("_make_client should NOT be called for sentinel-bytea PAT")

    monkeypatch.setattr(profile_sync, "_make_client", _fail_if_called)

    with pytest.raises(PATRejected, match="PAT not set"):
        await sync_profile(DEFAULT_UUID, _make_app_state(db_pool))
    assert call_count == [], "Pitfall 8: an HTTP client was constructed for a sentinel PAT"

    # 3. The DB state was also updated: status='failed' + error='pat_rejected'.
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT last_sync_status, last_sync_error, app_token_revoked "
            "FROM gruvax.profiles WHERE id = %s::uuid",
            (DEFAULT_UUID,),
        )
        row = await cur.fetchone()
        assert row == ("failed", "pat_rejected", True)

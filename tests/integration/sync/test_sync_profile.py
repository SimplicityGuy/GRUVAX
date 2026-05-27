"""Integration tests for sync_profile — Plan 01-03 Task 1.

Behaviours under test (11 tests, mirrors PLAN.md):
  1. Happy path: empty profile_collection → 450 rows after sync.
  2. Replaces existing rows atomically (DELETE + INSERT in one TX).
  3. PK composite (folder_id duplicates allowed): same release_id in two
     folders survives the swap.
  4. Advisory lock: concurrent sync raises SyncInProgress.
  5. PATRejected (401) → app_token_revoked=TRUE, status='failed',
     error='pat_rejected'.
  6. 5xx exhausted → ServerError → error='server_error'.
  7. 429 exhausted → RateLimitExhausted → error='rate_limited'.
  8. Network error → NetworkError → error='network'.
  9. discogsography_user_id COALESCE: pre-existing user_id is preserved.
 10. D-04: release_id is BIGINT (13-digit overflow tolerated).
 11. Lock released on unexpected exception (try/finally).

Each test runs against a live Postgres (db_pool fixture). The pre-flight
INSERT into gruvax.profiles uses a real Fernet-encrypted test PAT; the
DiscogsographyClient is constructed by sync_profile itself and routed to
the in-process FAKE app via a `_make_client` monkeypatch hook.
"""

from __future__ import annotations

import asyncio
import os
import types
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import psycopg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from gruvax._internal.fake_discogsography import create_fake_app
from gruvax.discogsography.client import DiscogsographyClient
from gruvax.discogsography.errors import (
    NetworkError,
    PATRejected,
    RateLimitExhausted,
    ServerError,
    SyncInProgress,
)
from gruvax.settings import settings
from gruvax.sync import profile_sync
from gruvax.sync.pat_crypto import encrypt_pat
from gruvax.sync.profile_sync import sync_profile


if TYPE_CHECKING:
    from collections.abc import AsyncIterator


DEFAULT_UUID = "00000000-0000-0000-0000-000000000001"
TEST_PAT = "dscg_test_pat_LEAK_DETECTOR_secret_aaa"


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_release(release_id: int, *, folder_id: int = 1, label: str = "Blue Note") -> dict:
    """Build a canonical fake-discogsography release envelope item."""
    return {
        "id": str(release_id),
        "title": f"Title {release_id}",
        "year": 1960 + (release_id % 50),
        "catalog_number": f"BLP-{release_id:04d}",
        "artist": f"Artist {release_id}",
        "label": label,
        "folder_id": folder_id,
    }


def _conninfo() -> str:
    return settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)


async def _seed_default_profile(db_pool, encrypted: bytes | None = None) -> None:  # type: ignore[no-untyped-def]
    """Reset the default profile to a clean (revoked=FALSE, no last_sync_*) state.

    The migration seed gives us `app_token_revoked=TRUE` + `'\\x'` placeholder.
    Tests that exercise the sync flow need a real Fernet-encrypted PAT and a
    clean status. This helper UPSERTs both.
    """
    cipher = encrypted if encrypted is not None else encrypt_pat(TEST_PAT)
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.profiles "
            "SET app_token_encrypted = %s, app_token_revoked = FALSE, "
            "    last_sync_status = NULL, last_sync_error = NULL, "
            "    last_sync_at = NULL, last_sync_item_count = NULL, "
            "    discogsography_user_id = NULL "
            "WHERE id = %s::uuid",
            (cipher, DEFAULT_UUID),
        )
        await conn.commit()


async def _truncate_profile_collection(db_pool) -> None:  # type: ignore[no-untyped-def]
    async with db_pool.connection() as conn:
        await conn.execute(
            "DELETE FROM gruvax.profile_collection WHERE profile_id = %s::uuid",
            (DEFAULT_UUID,),
        )
        await conn.commit()


def _make_app_state(db_pool) -> types.SimpleNamespace:  # type: ignore[no-untyped-def]
    """Build a minimal app_state with the four cache hooks as AsyncMock.

    Task 1 tests don't assert reload semantics; Task 2 tests use real
    instances. Task 1's mock suffices to keep the sync_profile call path
    runnable without dragging in BoundaryCache / SegmentCache plumbing.
    """
    snapshot = AsyncMock()
    snapshot.invalidate = lambda: None  # sync method
    boundary = AsyncMock()
    segment = AsyncMock()
    segment.derive = lambda *a, **kw: None  # sync method
    # boundary_cache.overrides is a dict in real code
    boundary.overrides = {}
    return types.SimpleNamespace(
        db_pool=db_pool,
        collection_snapshot=snapshot,
        boundary_cache=boundary,
        segment_cache=segment,
    )


def _client_factory_for(app) -> "type[DiscogsographyClient]":
    """Build a factory that returns a DiscogsographyClient routed at `app`.

    The factory mirrors the DiscogsographyClient constructor signature so
    the production code can be substituted without touching its API.
    """

    def _factory(base_url: str, pat: str) -> DiscogsographyClient:
        client = DiscogsographyClient(base_url=base_url, pat=pat)
        transport = ASGITransport(app=app)
        # Replace the inner httpx client with one bound to the in-process fake.
        # NB: the prod constructor sets headers={"Authorization": f"Bearer {pat}"}.
        async def _aclose_then_new() -> None:
            await client._client.aclose()

        # Schedule the close on the same loop the caller is using.
        loop = asyncio.get_event_loop()
        loop.create_task(_aclose_then_new())
        client._client = AsyncClient(
            transport=transport,
            base_url="http://fake",
            headers={"Authorization": f"Bearer {pat}"},
        )
        return client

    return _factory  # type: ignore[return-value]


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _ensure_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guarantee GRUVAX_SECRET_KEY is set (Fernet round-trip helpers need it)."""
    if not os.environ.get("GRUVAX_SECRET_KEY"):
        from cryptography.fernet import Fernet

        monkeypatch.setenv("GRUVAX_SECRET_KEY", Fernet.generate_key().decode())


@pytest_asyncio.fixture
async def clean_db(db_pool) -> "AsyncIterator[None]":  # type: ignore[no-untyped-def]
    """Reset profiles + profile_collection to a known starting state."""
    await _seed_default_profile(db_pool)
    await _truncate_profile_collection(db_pool)
    yield
    # No teardown — next test re-seeds.


# ── tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_sync_happy_path_450_rows(db_pool, clean_db, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    """Test 1: happy path — empty → 450 rows; status='ok'; item_count==450."""
    seed = [_make_release(i) for i in range(1, 451)]
    app = create_fake_app(seed=seed, user_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    monkeypatch.setattr(profile_sync, "_make_client", _client_factory_for(app))

    result = await sync_profile(DEFAULT_UUID, _make_app_state(db_pool))

    assert result["status"] == "ok"
    assert result["item_count"] == 450
    assert "took_ms" in result
    assert result["user_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT COUNT(*) FROM gruvax.profile_collection WHERE profile_id = %s::uuid",
            (DEFAULT_UUID,),
        )
        row = await cur.fetchone()
        assert row[0] == 450

        await cur.execute(
            "SELECT last_sync_status, last_sync_item_count, last_sync_at IS NOT NULL "
            "FROM gruvax.profiles WHERE id = %s::uuid",
            (DEFAULT_UUID,),
        )
        prow = await cur.fetchone()
        assert prow == ("ok", 450, True)


@pytest.mark.asyncio(loop_scope="session")
async def test_sync_replaces_existing_rows_atomically(  # type: ignore[no-untyped-def]
    db_pool, clean_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 2: pre-existing rows are atomically replaced by the new sync."""
    # Pre-populate 100 rows.
    async with db_pool.connection() as conn:
        for i in range(1, 101):
            await conn.execute(
                "INSERT INTO gruvax.profile_collection "
                "(profile_id, release_id, folder_id, artist, title, label, catalog_number, year) "
                "VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s)",
                (DEFAULT_UUID, 90000 + i, 1, f"Old {i}", f"Old Title {i}", "Old Label", f"OLD-{i:03d}", 2000),
            )
        await conn.commit()

    seed = [_make_release(i) for i in range(1, 451)]
    app = create_fake_app(seed=seed)
    monkeypatch.setattr(profile_sync, "_make_client", _client_factory_for(app))

    result = await sync_profile(DEFAULT_UUID, _make_app_state(db_pool))
    assert result["status"] == "ok"
    assert result["item_count"] == 450

    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT COUNT(*) FROM gruvax.profile_collection WHERE profile_id = %s::uuid",
            (DEFAULT_UUID,),
        )
        assert (await cur.fetchone())[0] == 450
        # None of the old release_ids (90001..90100) survive.
        await cur.execute(
            "SELECT COUNT(*) FROM gruvax.profile_collection "
            "WHERE profile_id = %s::uuid AND release_id >= 90001",
            (DEFAULT_UUID,),
        )
        assert (await cur.fetchone())[0] == 0


@pytest.mark.asyncio(loop_scope="session")
async def test_sync_folder_id_duplicates_allowed(  # type: ignore[no-untyped-def]
    db_pool, clean_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 3: D-03 composite PK — same release_id with different folder_id OK."""
    seed = [
        _make_release(12345, folder_id=1, label="Blue Note"),
        _make_release(12345, folder_id=99, label="Blue Note"),  # wantlist-archive
        _make_release(67890, folder_id=1),
    ]
    app = create_fake_app(seed=seed)
    monkeypatch.setattr(profile_sync, "_make_client", _client_factory_for(app))

    result = await sync_profile(DEFAULT_UUID, _make_app_state(db_pool))
    assert result["item_count"] == 3

    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT folder_id FROM gruvax.profile_collection "
            "WHERE profile_id = %s::uuid AND release_id = 12345 ORDER BY folder_id",
            (DEFAULT_UUID,),
        )
        rows = await cur.fetchall()
        assert [r[0] for r in rows] == [1, 99]


@pytest.mark.asyncio(loop_scope="session")
async def test_sync_concurrent_raises_sync_in_progress(  # type: ignore[no-untyped-def]
    db_pool, clean_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 4: pg_try_advisory_lock — concurrent sync raises SyncInProgress."""
    # Pre-acquire the advisory lock on a dedicated connection so the test
    # doesn't have to race against a slow fake. The lock_key derivation is
    # private to profile_sync; we replicate it.
    from gruvax.sync.profile_sync import _lock_key

    lock_key = _lock_key(DEFAULT_UUID)

    seed = [_make_release(i) for i in range(1, 6)]
    app = create_fake_app(seed=seed)
    monkeypatch.setattr(profile_sync, "_make_client", _client_factory_for(app))

    # Take the lock on an external connection.
    holder = await psycopg.AsyncConnection.connect(_conninfo())
    try:
        async with holder.cursor() as cur:
            await cur.execute("SELECT pg_try_advisory_lock(%s)", (lock_key,))
            row = await cur.fetchone()
            assert row[0] is True

        # Now sync should fail with SyncInProgress.
        with pytest.raises(SyncInProgress):
            await sync_profile(DEFAULT_UUID, _make_app_state(db_pool))
    finally:
        async with holder.cursor() as cur:
            await cur.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))
        await holder.close()


@pytest.mark.asyncio(loop_scope="session")
async def test_sync_pat_rejected_flips_revoked(  # type: ignore[no-untyped-def]
    db_pool, clean_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 5: 401/403 → PATRejected; app_token_revoked=TRUE; status='failed'."""

    # Build a fake that always returns 401, regardless of the bearer.
    from fastapi import FastAPI, HTTPException

    app = FastAPI()

    @app.get("/api/user/collection")
    async def _always_401() -> dict:
        raise HTTPException(status_code=401, detail="Token rejected")

    monkeypatch.setattr(profile_sync, "_make_client", _client_factory_for(app))

    with pytest.raises(PATRejected):
        await sync_profile(DEFAULT_UUID, _make_app_state(db_pool))

    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT last_sync_status, last_sync_error, app_token_revoked "
            "FROM gruvax.profiles WHERE id = %s::uuid",
            (DEFAULT_UUID,),
        )
        row = await cur.fetchone()
        assert row == ("failed", "pat_rejected", True)


@pytest.mark.asyncio(loop_scope="session")
async def test_sync_server_error_tag(  # type: ignore[no-untyped-def]
    db_pool, clean_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 6: 5xx exhausted → ServerError; last_sync_error='server_error'."""
    from fastapi import FastAPI, HTTPException

    app = FastAPI()

    @app.get("/api/user/collection")
    async def _always_500() -> dict:
        raise HTTPException(status_code=500, detail="boom")

    monkeypatch.setattr(profile_sync, "_make_client", _client_factory_for(app))

    with pytest.raises(ServerError):
        await sync_profile(DEFAULT_UUID, _make_app_state(db_pool))

    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT last_sync_status, last_sync_error, app_token_revoked "
            "FROM gruvax.profiles WHERE id = %s::uuid",
            (DEFAULT_UUID,),
        )
        row = await cur.fetchone()
        assert row[0] == "failed"
        assert row[1] == "server_error"
        # app_token_revoked must NOT be flipped on a 5xx.
        assert row[2] is False


@pytest.mark.asyncio(loop_scope="session")
async def test_sync_rate_limited_tag(  # type: ignore[no-untyped-def]
    db_pool, clean_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 7: 429 exhausted → RateLimitExhausted; last_sync_error='rate_limited'."""
    from fastapi import FastAPI, HTTPException

    app = FastAPI()

    @app.get("/api/user/collection")
    async def _always_429() -> dict:
        raise HTTPException(status_code=429, headers={"Retry-After": "1"}, detail="slow down")

    monkeypatch.setattr(profile_sync, "_make_client", _client_factory_for(app))

    with pytest.raises(RateLimitExhausted):
        await sync_profile(DEFAULT_UUID, _make_app_state(db_pool))

    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT last_sync_status, last_sync_error FROM gruvax.profiles WHERE id = %s::uuid",
            (DEFAULT_UUID,),
        )
        row = await cur.fetchone()
        assert row == ("failed", "rate_limited")


@pytest.mark.asyncio(loop_scope="session")
async def test_sync_network_error_tag(  # type: ignore[no-untyped-def]
    db_pool, clean_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 8: ConnectError exhausted → NetworkError; last_sync_error='network'."""
    import httpx

    class _AlwaysFails(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("simulated network failure")

    def _make_failing_client(base_url: str, pat: str) -> DiscogsographyClient:
        client = DiscogsographyClient(base_url=base_url, pat=pat)
        # Schedule close of the prod client to avoid resource warnings.
        asyncio.get_event_loop().create_task(client._client.aclose())
        client._client = httpx.AsyncClient(
            transport=_AlwaysFails(),
            base_url="http://fake",
            headers={"Authorization": f"Bearer {pat}"},
        )
        return client

    monkeypatch.setattr(profile_sync, "_make_client", _make_failing_client)

    with pytest.raises(NetworkError):
        await sync_profile(DEFAULT_UUID, _make_app_state(db_pool))

    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT last_sync_status, last_sync_error FROM gruvax.profiles WHERE id = %s::uuid",
            (DEFAULT_UUID,),
        )
        row = await cur.fetchone()
        assert row == ("failed", "network")


@pytest.mark.asyncio(loop_scope="session")
async def test_sync_user_id_coalesce_preserves_existing(  # type: ignore[no-untyped-def]
    db_pool, clean_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 9: COALESCE — existing discogsography_user_id wins over response value."""
    # 1) First sync sets the user_id.
    seed = [_make_release(i) for i in range(1, 11)]
    captured_uuid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    app1 = create_fake_app(seed=seed, user_id=captured_uuid)
    monkeypatch.setattr(profile_sync, "_make_client", _client_factory_for(app1))
    await sync_profile(DEFAULT_UUID, _make_app_state(db_pool))

    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT discogsography_user_id::text FROM gruvax.profiles WHERE id = %s::uuid",
            (DEFAULT_UUID,),
        )
        assert (await cur.fetchone())[0] == captured_uuid

    # 2) Second sync from a fake with a DIFFERENT user_id — captured stays the same.
    other_uuid = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    app2 = create_fake_app(seed=seed, user_id=other_uuid)
    monkeypatch.setattr(profile_sync, "_make_client", _client_factory_for(app2))
    await sync_profile(DEFAULT_UUID, _make_app_state(db_pool))

    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT discogsography_user_id::text FROM gruvax.profiles WHERE id = %s::uuid",
            (DEFAULT_UUID,),
        )
        # COALESCE: original value preserved despite the second response shipping `other_uuid`.
        assert (await cur.fetchone())[0] == captured_uuid


@pytest.mark.asyncio(loop_scope="session")
async def test_sync_release_id_bigint_overflow(  # type: ignore[no-untyped-def]
    db_pool, clean_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 10: D-04 — release_id stored as BIGINT survives 13-digit ids."""
    big_id = 9999999999999  # 13 digits, > 2^31, < 2^63
    seed = [{
        "id": str(big_id),
        "title": "Big",
        "year": 2020,
        "catalog_number": "BIG-001",
        "artist": "Big Artist",
        "label": "Big Label",
        "folder_id": 1,
    }]
    app = create_fake_app(seed=seed)
    monkeypatch.setattr(profile_sync, "_make_client", _client_factory_for(app))
    result = await sync_profile(DEFAULT_UUID, _make_app_state(db_pool))
    assert result["item_count"] == 1

    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT release_id FROM gruvax.profile_collection WHERE profile_id = %s::uuid",
            (DEFAULT_UUID,),
        )
        row = await cur.fetchone()
        assert row[0] == big_id


@pytest.mark.asyncio(loop_scope="session")
async def test_sync_lock_released_on_unexpected_exception(  # type: ignore[no-untyped-def]
    db_pool, clean_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 11: try/finally releases the advisory lock even on a non-typed crash."""

    # Build a client whose first_page raises an arbitrary RuntimeError.
    class _ExplodingClient:
        async def first_page(self) -> dict:
            raise RuntimeError("non-typed mid-fetch boom")

        async def _get_page(self, *, limit: int, offset: int) -> dict:
            raise RuntimeError("non-typed mid-fetch boom")

        async def aclose(self) -> None:
            pass

    def _factory(base_url: str, pat: str):  # type: ignore[no-untyped-def]
        return _ExplodingClient()

    monkeypatch.setattr(profile_sync, "_make_client", _factory)

    with pytest.raises(RuntimeError):
        await sync_profile(DEFAULT_UUID, _make_app_state(db_pool))

    # The lock must be releasable from a fresh connection now.
    from gruvax.sync.profile_sync import _lock_key

    lock_key = _lock_key(DEFAULT_UUID)
    conn = await psycopg.AsyncConnection.connect(_conninfo())
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT pg_try_advisory_lock(%s)", (lock_key,))
            acquired = (await cur.fetchone())[0]
            assert acquired is True, "advisory lock was not released by sync_profile finally"
            await cur.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))
    finally:
        await conn.close()

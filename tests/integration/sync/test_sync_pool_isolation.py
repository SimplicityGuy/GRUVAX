"""Pool-isolation observable test — Plan 01-03 Task 2 Test 7 (Pitfall 6).

The critical safety property: sync_profile uses a DEDICATED
psycopg.AsyncConnection.connect() for the multi-second collection sync.
It must NEVER hold a pool slot for the duration of the sync — otherwise
a 2-slot pool starves on a single in-flight sync.

This test proves the property via OBSERVABLE behavior:
  1. Construct a tiny pool (max_size=2).
  2. Start sync_profile() in a background task with a slow fake (sleeps
     between pages).
  3. Concurrently fire 3 short pool.connection() checkouts.
  4. All 3 checkouts MUST complete within 500ms; sync continues running.

If sync_profile is holding a pool slot, only 1 of the 3 concurrent
checkouts succeeds in time; the other 2 wait for the sync to complete
(seconds). The test fails the moment any checkout times out — the
regression surface for Pitfall 6.
"""

from __future__ import annotations

import asyncio
import os
import time
import types
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

from fastapi import FastAPI, Header, HTTPException, Query
from httpx import ASGITransport, AsyncClient
from psycopg_pool import AsyncConnectionPool
import pytest
import pytest_asyncio

from gruvax.discogsography.client import DiscogsographyClient
from gruvax.settings import settings
from gruvax.sync import profile_sync
from gruvax.sync.pat_crypto import encrypt_pat
from gruvax.sync.profile_sync import sync_profile


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from typing import Any


DEFAULT_UUID = "00000000-0000-0000-0000-000000000001"
TEST_PAT = "dscg_test_pat_LEAK_DETECTOR_secret_aaa"


def _conninfo() -> str:
    return settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)


def _make_slow_fake_app(
    *, seed_pages: int = 5, page_size: int = 200, page_sleep_s: float = 0.5
) -> FastAPI:
    """A fake-discogsography app that sleeps `page_sleep_s` between page fetches.

    Total sync time ≈ seed_pages * page_sleep_s. With defaults that's ~2.5s —
    enough to observe pool-checkout races without making the test slow.
    """
    app = FastAPI()
    total_rows = seed_pages * page_size
    rows = [
        {
            "id": str(i),
            "title": f"Slow {i}",
            "year": 1980,
            "catalog_number": f"SLW-{i:04d}",
            "artist": "Slow Artist",
            "label": "Slow Label",
            "folder_id": 1,
        }
        for i in range(1, total_rows + 1)
    ]

    @app.get("/api/user/collection")
    async def _slow_collection(
        authorization: str | None = Header(default=None),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> dict:
        if not authorization or not authorization.startswith("Bearer dscg_"):
            raise HTTPException(401)
        # Sleep BEFORE returning so the pool-checkout test has time to fire.
        await asyncio.sleep(page_sleep_s)
        page = rows[offset : offset + limit]
        return {
            "user_id": "55555555-5555-5555-5555-555555555555",
            "releases": page,
            "total": len(rows),
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(page) < len(rows),
        }

    return app


def _client_factory_for(app):  # type: ignore[no-untyped-def]
    def _factory(base_url: str, pat: str) -> DiscogsographyClient:
        client = DiscogsographyClient.__new__(DiscogsographyClient)
        client._client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://fake",
            headers={"Authorization": f"Bearer {pat}"},
        )
        return client

    return _factory


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _ensure_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    if not os.environ.get("GRUVAX_SECRET_KEY"):
        from cryptography.fernet import Fernet

        monkeypatch.setenv("GRUVAX_SECRET_KEY", Fernet.generate_key().decode())


@pytest_asyncio.fixture(loop_scope="session")
async def tiny_pool() -> AsyncIterator[AsyncConnectionPool[Any]]:
    """A dedicated AsyncConnectionPool with max_size=2 — separate from db_pool.

    Using a tiny pool makes the regression test sharper: if sync_profile
    consumes 1 of 2 slots, the 3-concurrent-checkout assertion fails fast.
    """
    pool = AsyncConnectionPool(
        conninfo=_conninfo(),
        min_size=1,
        max_size=2,
        open=False,
    )
    await pool.open()
    yield pool
    await pool.close()


@pytest_asyncio.fixture(loop_scope="session")
async def _prep_default_profile(db_pool) -> AsyncIterator[None]:  # type: ignore[no-untyped-def]
    """Reset the default profile to a sync-runnable state."""
    cipher = encrypt_pat(TEST_PAT)
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.profiles SET "
            "    app_token_encrypted = %s, app_token_revoked = FALSE, "
            "    last_sync_status = NULL, last_sync_error = NULL "
            "WHERE id = %s::uuid",
            (cipher, DEFAULT_UUID),
        )
        await conn.execute(
            "DELETE FROM gruvax.profile_collection WHERE profile_id = %s::uuid",
            (DEFAULT_UUID,),
        )
        await conn.commit()
    yield


# ── tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_concurrent_pool_checkouts_unblocked_during_sync(  # type: ignore[no-untyped-def]
    tiny_pool, _prep_default_profile, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pitfall 6: sync_profile MUST NOT hold a pool slot during the sync body.

    Observable check: while a multi-second sync is in flight against the
    tiny_pool, three concurrent `tiny_pool.connection()` checkouts must
    all complete within 500ms each. Any timeout fails the test — that's
    the Pitfall 6 regression surface.
    """
    slow_app = _make_slow_fake_app(seed_pages=5, page_size=200, page_sleep_s=0.5)
    monkeypatch.setattr(profile_sync, "_make_client", _client_factory_for(slow_app))

    from gruvax.events.bus import EventBus

    snapshot = AsyncMock()
    snapshot.invalidate = lambda: None
    boundary = AsyncMock()
    boundary.invalidate = lambda: None
    boundary.overrides = {}
    segment = AsyncMock()
    segment.derive = lambda *a, **kw: None
    app_state = types.SimpleNamespace(
        db_pool=tiny_pool,
        boundary_cache_registry={DEFAULT_UUID: boundary},
        snapshot_registry={DEFAULT_UUID: snapshot},
        segment_cache_registry={DEFAULT_UUID: segment},
        event_bus_registry={DEFAULT_UUID: EventBus()},
    )

    # Start the sync in the background.
    sync_task = asyncio.create_task(sync_profile(DEFAULT_UUID, app_state))
    try:
        # Give the sync a moment to start (acquire its dedicated conn + first page).
        await asyncio.sleep(0.2)

        # Fire 3 concurrent pool checkouts; each must complete within 500ms.
        async def _checkout(idx: int) -> tuple[int, float, int]:
            t0 = time.perf_counter()
            async with tiny_pool.connection(timeout=0.5) as conn, conn.cursor() as cur:
                await cur.execute("SELECT %s::int", (idx,))
                row = await cur.fetchone()
            return (idx, time.perf_counter() - t0, int(row[0]))

        results = await asyncio.gather(
            _checkout(1),
            _checkout(2),
            _checkout(3),
            return_exceptions=True,
        )

        # All checkouts must have succeeded.
        for r in results:
            if isinstance(r, BaseException):
                pytest.fail(
                    "Pitfall 6 regression: pool checkout failed while sync was "
                    f"in flight (sync is holding a pool slot): {r!r}"
                )
        for idx, took, val in results:  # type: ignore[misc]
            assert val == idx
            assert took < 0.5, (
                f"Pitfall 6 regression: checkout #{idx} took {took:.3f}s "
                f"(should be <0.5s if sync is using a dedicated conn)"
            )
    finally:
        # Drain the sync task to keep teardown clean.
        await sync_task

"""Real SQL/HTTP redemption failures preserve invites; commit is race-safe."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import psycopg
import pytest
import pytest_asyncio

from gruvax.api import invite_codes
from gruvax.api.admin.limiter import limiter
from gruvax.api.admin.profiles import router as profiles_router
from gruvax.api.deps import require_admin
from gruvax.discogsography.errors import NetworkError, PATRejected, RateLimitExhausted, ServerError
from gruvax.sync.pat_crypto import decrypt_pat


if TYPE_CHECKING:
    from collections.abc import AsyncIterator

PAT = "dscg_synthetic_invite_pat_".ljust(50, "x")


class TrackedCursor:
    def __init__(self, raw: Any, tracker: TrackedPool) -> None:
        self.raw = raw
        self.tracker = tracker
        self.query = ""

    async def __aenter__(self) -> TrackedCursor:
        await self.raw.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> Any:
        return await self.raw.__aexit__(*args)

    async def execute(self, query: str, params: Any = None) -> None:
        self.query = query
        try:
            await self.raw.execute(query, params)
        except psycopg.errors.UniqueViolation:
            self.tracker.unique_violations += 1
            raise

    async def fetchone(self) -> Any:
        row = await self.raw.fetchone()
        if self.tracker.collision_barrier and "SELECT id::text" in self.query:
            await asyncio.wait_for(self.tracker.collision_barrier.wait(), 5)
        if self.tracker.collision_callback and "SELECT id::text" in self.query:
            callback = self.tracker.collision_callback
            self.tracker.collision_callback = None
            await callback()
        return row

    def __getattr__(self, name: str) -> Any:
        return getattr(self.raw, name)


class TrackedConnection:
    def __init__(self, raw: Any, tracker: TrackedPool) -> None:
        self.raw = raw
        self.tracker = tracker

    def cursor(self) -> TrackedCursor:
        return TrackedCursor(self.raw.cursor(), self.tracker)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.raw, name)


class TrackedPool:
    def __init__(self, raw: Any) -> None:
        self.raw = raw
        self.held: dict[Any, int] = {}
        self.collision_barrier: asyncio.Barrier | None = None
        self.unique_violations = 0
        self.collision_callback: Any = None

    @property
    def in_use(self) -> int:
        return self.held.get(asyncio.current_task(), 0)

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[TrackedConnection]:
        async with self.raw.connection() as conn:
            task = asyncio.current_task()
            self.held[task] = self.held.get(task, 0) + 1
            try:
                yield TrackedConnection(conn, self)
            finally:
                self.held[task] -= 1


@pytest_asyncio.fixture(loop_scope="session")
async def redemption(db_pool: Any, monkeypatch: Any) -> AsyncIterator[Any]:
    limiter.reset()
    ids = [str(uuid4()) for _ in range(3)]
    codes = [str(uuid4()) for _ in range(2)]
    async with db_pool.connection() as conn:
        for pid in ids:
            await conn.execute(
                "INSERT INTO gruvax.profiles (id,display_name,app_token_encrypted,app_token_revoked)"
                " VALUES (%s,%s,%s,TRUE)",
                (pid, "Invite test " + pid, b""),
            )
        for code, pid in zip(codes, ids, strict=False):
            await conn.execute(
                "INSERT INTO gruvax.profile_invite_codes (code,profile_id,expires_at)"
                " VALUES (%s,%s,NOW()+INTERVAL '1 hour')",
                (code, pid),
            )
    pool = TrackedPool(db_pool)
    queued = AsyncMock()
    monkeypatch.setattr(invite_codes, "_run_sync_background", queued)
    app = FastAPI()
    app.state.db_pool = pool
    app.include_router(invite_codes.public_router, prefix="/api")
    app.include_router(profiles_router, prefix="/api/admin")
    app.dependency_overrides[require_admin] = lambda: {}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, pool, ids, codes, queued
    finally:
        async with db_pool.connection() as conn:
            await conn.execute("DELETE FROM gruvax.profiles WHERE id=ANY(%s::uuid[])", (ids,))


async def state(pool: Any, code: str, pid: str) -> Any:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT pic.consumed_at, p.app_token_encrypted, p.app_token_revoked,"
            " p.discogsography_user_id FROM gruvax.profile_invite_codes pic"
            " JOIN gruvax.profiles p ON p.id=pic.profile_id WHERE pic.code=%s AND p.id=%s",
            (code, pid),
        )
        return await cur.fetchone()


async def post(client: AsyncClient, code: str) -> Any:
    return await client.post(f"/api/invite-codes/{code}/redeem", json={"pat": PAT})


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(
    "error,status",
    [(PATRejected, 401), (RateLimitExhausted, 503), (ServerError, 503), (NetworkError, 503)],
)
async def test_upstream_failure_preserves_invite_and_retry_succeeds(
    redemption: Any, monkeypatch: Any, error: Any, status: int
) -> None:
    client, pool, ids, codes, queued = redemption

    async def failed(pat: str) -> str:
        assert pool.in_use == 0, "HTTP validation must not retain a DB slot"
        raise error()

    monkeypatch.setattr(invite_codes, "_run_test_sync", failed)
    result = await post(client, codes[0])
    assert result.status_code == status
    assert PAT not in result.text
    assert await state(pool.raw, codes[0], ids[0]) == (None, b"", True, None)
    queued.assert_not_awaited()
    uid = str(uuid4())

    async def accepted(pat: str) -> str:
        assert pool.in_use == 0
        return uid

    monkeypatch.setattr(invite_codes, "_run_test_sync", accepted)
    assert (await post(client, codes[0])).status_code == 200
    consumed, ciphertext, revoked, user = await state(pool.raw, codes[0], ids[0])
    assert consumed is not None and revoked is False and str(user) == uid
    assert decrypt_pat(ciphertext) == PAT
    queued.assert_awaited_once()
    assert (await post(client, codes[0])).status_code == 404


@pytest.mark.asyncio(loop_scope="session")
async def test_collision_rolls_back_consumption(redemption: Any, monkeypatch: Any) -> None:
    client, pool, ids, codes, queued = redemption
    uid = str(uuid4())
    async with pool.raw.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.profiles SET discogsography_user_id=%s WHERE id=%s", (uid, ids[2])
        )
    monkeypatch.setattr(invite_codes, "_run_test_sync", AsyncMock(return_value=uid))
    assert (await post(client, codes[0])).status_code == 409
    assert await state(pool.raw, codes[0], ids[0]) == (None, b"", True, None)
    queued.assert_not_awaited()
    async with pool.raw.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.profiles SET discogsography_user_id=NULL WHERE id=%s", (ids[2],)
        )
    assert (await post(client, codes[0])).status_code == 200


@pytest.mark.asyncio(loop_scope="session")
async def test_simultaneous_same_invite_has_one_winner(redemption: Any, monkeypatch: Any) -> None:
    client, pool, ids, codes, queued = redemption
    barrier = asyncio.Barrier(2)
    uid = str(uuid4())

    async def accepted(pat: str) -> str:
        assert pool.in_use == 0
        await asyncio.wait_for(barrier.wait(), 5)
        return uid

    monkeypatch.setattr(invite_codes, "_run_test_sync", accepted)
    results = await asyncio.gather(post(client, codes[0]), post(client, codes[0]))
    assert sorted(r.status_code for r in results) == [200, 404]
    queued.assert_awaited_once()
    assert decrypt_pat((await state(pool.raw, codes[0], ids[0]))[1]) == PAT


@pytest.mark.asyncio(loop_scope="session")
async def test_raced_unique_collision_returns_409_and_keeps_losing_invite(
    redemption: Any, monkeypatch: Any
) -> None:
    client, pool, ids, codes, queued = redemption
    pool.collision_barrier = asyncio.Barrier(2)
    monkeypatch.setattr(invite_codes, "_run_test_sync", AsyncMock(return_value=str(uuid4())))
    results = await asyncio.gather(post(client, codes[0]), post(client, codes[1]))
    assert sorted(r.status_code for r in results) == [200, 409]
    assert pool.unique_violations == 1, "both real SELECTs ran before either unique-index write"
    queued.assert_awaited_once()
    loser = next(i for i, r in enumerate(results) if r.status_code == 409)
    assert await state(pool.raw, codes[loser], ids[loser]) == (None, b"", True, None)


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("timing", ["before", "during_http", "after_consume"])
async def test_deleted_profile_never_consumes_or_connects(
    redemption: Any, monkeypatch: Any, timing: str
) -> None:
    client, pool, ids, codes, queued = redemption
    uid = str(uuid4())

    async def delete_profile() -> None:
        assert (await client.delete(f"/api/admin/profiles/{ids[0]}")).status_code == 200

    async def accepted(pat: str) -> str:
        assert pool.in_use == 0
        if timing == "during_http":
            await delete_profile()
        return uid

    upstream = AsyncMock(side_effect=accepted)
    monkeypatch.setattr(invite_codes, "_run_test_sync", upstream)
    if timing == "before":
        await delete_profile()
    elif timing == "after_consume":
        # Real deletion commits after the final consume, before the token UPDATE.
        pool.collision_callback = delete_profile
    result = await post(client, codes[0])
    assert result.status_code == 404
    assert result.json() == {"detail": {"type": "invite_not_found"}}
    assert await state(pool.raw, codes[0], ids[0]) == (None, b"", True, None)
    queued.assert_not_awaited()
    if timing == "before":
        upstream.assert_not_awaited()
    else:
        upstream.assert_awaited_once()

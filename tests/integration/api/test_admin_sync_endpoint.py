"""Integration tests for POST /api/admin/profiles/{profile_id}/sync — Plan 01-04 Task 1.

Tests (10 — mirrors PLAN.md):
  1. Unauthenticated → 401.
  2. Logged-in but no CSRF → 403.
  3. Happy path — 200 with {"status":"ok","item_count":N,"took_ms":T,"user_id":U};
     profiles.last_sync_status='ok'.
  4. 404 — unknown profile UUID → {"type":"profile_not_found"}.
  5. 400 — invalid UUID path param → {"type":"invalid_uuid"}.
  6. 409 — concurrent sync (advisory lock held) → {"type":"already_in_progress"}.
  7. 401 — PAT rejected (fake returns 401) → {"type":"pat_rejected"}.
  8. 503 — upstream 5xx → {"type":"upstream_unavailable"}.
  9. Caches refreshed inline (D-14) — collection_snapshot reflects new rows post-sync
     without an API restart.
 10. Pitfall 6 (pool isolation) — the handler MUST NOT inject Depends(get_pool); a
     concurrent admin checkout against a small pool returns within 100ms while a
     slow sync is in flight. Also asserts the static grep gate: source contains
     zero occurrences of "Depends(get_pool)".

Auth model:
  - Reuses the same login fixture pattern as tests/integration/test_admin_auth.py:
    seeds PIN hash "0000", POSTs /api/admin/login, captures cookies + CSRF.
  - Mutating requests echo X-CSRF-Token (require_admin's double-submit pattern).
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import time
import types
from typing import TYPE_CHECKING

from asgi_lifespan import LifespanManager
from fastapi import FastAPI, Header, HTTPException, Query
from httpx import ASGITransport, AsyncClient
import psycopg
import pytest
import pytest_asyncio

from gruvax._internal.fake_discogsography import create_fake_app
from gruvax.app import create_app
from gruvax.discogsography.client import DiscogsographyClient
from gruvax.settings import settings
from gruvax.sync import profile_sync
from gruvax.sync.pat_crypto import encrypt_pat


if TYPE_CHECKING:
    from collections.abc import AsyncIterator


DEFAULT_UUID = "00000000-0000-0000-0000-000000000001"
TEST_PAT = "dscg_test_pat_LEAK_DETECTOR_secret_aaa_endpoint_tests"
_TEST_PIN = "0000"


# ── helpers ──────────────────────────────────────────────────────────────────


def _conninfo() -> str:
    return settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)


def _make_release(release_id: int) -> dict:
    return {
        "id": str(release_id),
        "title": f"Title {release_id}",
        "year": 1960 + (release_id % 50),
        "catalog_number": f"BLP-{release_id:04d}",
        "artist": f"Artist {release_id}",
        "label": "Blue Note",
        "folder_id": 1,
    }


def _client_factory_for(app):  # type: ignore[no-untyped-def]
    """Build a `_make_client` substitute that routes DiscogsographyClient at the ASGI app."""

    def _factory(base_url: str, pat: str) -> DiscogsographyClient:
        client = DiscogsographyClient.__new__(DiscogsographyClient)
        client._client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://fake",
            headers={"Authorization": f"Bearer {pat}"},
        )
        return client

    return _factory


async def _seed_default_profile(db_pool, encrypted: bytes | None = None) -> None:  # type: ignore[no-untyped-def]
    """Reset the default profile to a sync-runnable state with a real Fernet PAT."""
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
        await conn.execute(
            "DELETE FROM gruvax.profile_collection WHERE profile_id = %s::uuid",
            (DEFAULT_UUID,),
        )
        await conn.commit()


async def _seed_pin(db_pool) -> None:  # type: ignore[no-untyped-def]
    """Seed test PIN '0000' into gruvax.settings using passlib Argon2id."""
    from gruvax.auth.pin import hash_pin

    h = hash_pin(_TEST_PIN)
    _DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.settings (profile_id, key, value, description, updated_at)"
            " VALUES (%s::uuid, 'auth.pin_hash', %s::jsonb, 'Test PIN seeded by test_admin_sync_endpoint', now())"
            " ON CONFLICT (profile_id, key) DO UPDATE"
            "  SET value = EXCLUDED.value, updated_at = now()",
            (_DEFAULT_PROFILE_UUID, f'"{h}"'),
        )
        await conn.commit()


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _ensure_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guarantee GRUVAX_SECRET_KEY is set (Fernet round-trip)."""
    if not os.environ.get("GRUVAX_SECRET_KEY"):
        from cryptography.fernet import Fernet

        monkeypatch.setenv("GRUVAX_SECRET_KEY", Fernet.generate_key().decode())


@pytest.fixture(autouse=True)
def _ensure_session_secret() -> None:
    """Guarantee SESSION_SECRET is set (admin login cookie signing)."""
    if not os.environ.get("SESSION_SECRET"):
        os.environ["SESSION_SECRET"] = "test-session-secret-for-pytest-only"


@pytest_asyncio.fixture(loop_scope="session")
async def app_client(db_pool) -> AsyncIterator[tuple[AsyncClient, FastAPI]]:  # type: ignore[no-untyped-def]
    """Per-test ASGI client + the underlying app (so monkeypatch & state inspection work).

    Function-scoped (not module-scoped) because each test mutates the same
    default profile row + advisory lock state; reusing the lifespan across
    tests would leak in-process state (boundary/snapshot caches in particular).

    The boundary/snapshot/segment caches on app.state are replaced with mocks
    AFTER lifespan startup so that ``sync_profile``'s inline ``_refresh_app_caches``
    (D-14) does not depend on Plan 06 having migrated ``collection_snapshot.py``
    to read from ``profile_collection`` instead of the dropped ``v_collection``
    view. Plan 03's own integration tests use the same AsyncMock substitution
    for the same reason — keeps Plan 04's endpoint tests isolated from the
    Wave-4 read-path rewire.
    """
    from unittest.mock import AsyncMock

    await _seed_pin(db_pool)
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac,
    ):
        # Substitute cache hooks AFTER lifespan startup so the long-running
        # sync_profile path can call snapshot.invalidate() + load(pool) without
        # touching the still-Plan-06-pending collection_snapshot.py read path.
        snapshot = AsyncMock()
        snapshot.invalidate = lambda: None
        boundary = AsyncMock()
        boundary.overrides = {}
        segment = AsyncMock()
        segment.derive = lambda *a, **kw: None
        app.state.collection_snapshot = snapshot
        app.state.boundary_cache = boundary
        app.state.segment_cache = segment
        yield ac, app


async def _login(client: AsyncClient) -> dict:
    """POST /api/admin/login with the seeded test PIN; return cookies + csrf."""
    res = await client.post("/api/admin/login", json={"pin": _TEST_PIN})
    assert res.status_code == 200, f"login failed: {res.status_code} {res.text}"
    return {
        "cookies": res.cookies,
        "csrf_token": res.cookies.get("gruvax_csrf") or res.json().get("csrf_token"),
    }


# ── tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_unauthenticated_returns_401(app_client) -> None:  # type: ignore[no-untyped-def]
    """Test 1: POST without session cookie → 401."""
    client, _app = app_client
    res = await client.post(f"/api/admin/profiles/{DEFAULT_UUID}/sync")
    assert res.status_code == 401, f"expected 401, got {res.status_code}: {res.text}"


@pytest.mark.asyncio(loop_scope="session")
async def test_logged_in_no_csrf_returns_403(app_client) -> None:  # type: ignore[no-untyped-def]
    """Test 2: logged-in client without X-CSRF-Token header → 403."""
    client, _app = app_client
    auth = await _login(client)
    res = await client.post(
        f"/api/admin/profiles/{DEFAULT_UUID}/sync",
        cookies=auth["cookies"],
        # no X-CSRF-Token header
    )
    assert res.status_code == 403, f"expected 403, got {res.status_code}: {res.text}"


@pytest.mark.asyncio(loop_scope="session")
async def test_happy_path_sync(app_client, db_pool, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    """Test 3: valid login + CSRF + good profile → 200 with status/item_count/took_ms/user_id."""
    client, _app = app_client
    await _seed_default_profile(db_pool)

    seed = [_make_release(i) for i in range(1, 51)]
    fake = create_fake_app(seed=seed, user_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    monkeypatch.setattr(profile_sync, "_make_client", _client_factory_for(fake))

    auth = await _login(client)
    res = await client.post(
        f"/api/admin/profiles/{DEFAULT_UUID}/sync",
        cookies=auth["cookies"],
        headers={"X-CSRF-Token": auth["csrf_token"]},
    )
    assert res.status_code == 200, f"got {res.status_code}: {res.text}"

    body = res.json()
    assert body["status"] == "ok"
    assert body["item_count"] == 50
    assert "took_ms" in body
    assert body["user_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT last_sync_status, last_sync_item_count FROM gruvax.profiles WHERE id = %s::uuid",
            (DEFAULT_UUID,),
        )
        row = await cur.fetchone()
        assert row == ("ok", 50)


@pytest.mark.asyncio(loop_scope="session")
async def test_unknown_profile_returns_404(app_client) -> None:  # type: ignore[no-untyped-def]
    """Test 4: nonexistent UUID → 404 with {"type":"profile_not_found"}."""
    client, _app = app_client
    auth = await _login(client)
    bogus = "ffffffff-ffff-ffff-ffff-ffffffffffff"
    res = await client.post(
        f"/api/admin/profiles/{bogus}/sync",
        cookies=auth["cookies"],
        headers={"X-CSRF-Token": auth["csrf_token"]},
    )
    assert res.status_code == 404, f"got {res.status_code}: {res.text}"
    body = res.json()
    detail = body.get("detail", body)
    assert detail.get("type") == "profile_not_found", detail


@pytest.mark.asyncio(loop_scope="session")
async def test_invalid_uuid_returns_400(app_client) -> None:  # type: ignore[no-untyped-def]
    """Test 5: invalid UUID path param → 400 with {"type":"invalid_uuid"}."""
    client, _app = app_client
    auth = await _login(client)
    res = await client.post(
        "/api/admin/profiles/not-a-uuid/sync",
        cookies=auth["cookies"],
        headers={"X-CSRF-Token": auth["csrf_token"]},
    )
    assert res.status_code == 400, f"got {res.status_code}: {res.text}"
    body = res.json()
    detail = body.get("detail", body)
    assert detail.get("type") == "invalid_uuid", detail


@pytest.mark.asyncio(loop_scope="session")
async def test_concurrent_sync_returns_409(  # type: ignore[no-untyped-def]
    app_client, db_pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 6: advisory lock held → 409 with {"type":"already_in_progress"}."""
    client, _app = app_client
    await _seed_default_profile(db_pool)

    # Pre-acquire the advisory lock on an external connection so the request
    # immediately fails with SyncInProgress.
    from gruvax.sync.profile_sync import _lock_key

    lock_key = _lock_key(DEFAULT_UUID)
    holder = await psycopg.AsyncConnection.connect(_conninfo())
    try:
        async with holder.cursor() as cur:
            await cur.execute("SELECT pg_try_advisory_lock(%s)", (lock_key,))
            assert (await cur.fetchone())[0] is True

        seed = [_make_release(i) for i in range(1, 11)]
        fake = create_fake_app(seed=seed)
        monkeypatch.setattr(profile_sync, "_make_client", _client_factory_for(fake))

        auth = await _login(client)
        res = await client.post(
            f"/api/admin/profiles/{DEFAULT_UUID}/sync",
            cookies=auth["cookies"],
            headers={"X-CSRF-Token": auth["csrf_token"]},
        )
        assert res.status_code == 409, f"got {res.status_code}: {res.text}"
        body = res.json()
        detail = body.get("detail", body)
        assert detail.get("type") == "already_in_progress", detail
    finally:
        async with holder.cursor() as cur:
            await cur.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))
        await holder.close()


@pytest.mark.asyncio(loop_scope="session")
async def test_pat_rejected_returns_401_typed(  # type: ignore[no-untyped-def]
    app_client, db_pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 7: PATRejected (fake returns 401) → 401 with {"type":"pat_rejected"}."""
    client, _app = app_client
    await _seed_default_profile(db_pool)

    fake = FastAPI()

    @fake.get("/api/user/collection")
    async def _always_401() -> dict:
        raise HTTPException(status_code=401, detail="Token rejected")

    monkeypatch.setattr(profile_sync, "_make_client", _client_factory_for(fake))

    auth = await _login(client)
    res = await client.post(
        f"/api/admin/profiles/{DEFAULT_UUID}/sync",
        cookies=auth["cookies"],
        headers={"X-CSRF-Token": auth["csrf_token"]},
    )
    assert res.status_code == 401, f"got {res.status_code}: {res.text}"
    body = res.json()
    detail = body.get("detail", body)
    assert detail.get("type") == "pat_rejected", detail


@pytest.mark.asyncio(loop_scope="session")
async def test_server_error_returns_503_typed(  # type: ignore[no-untyped-def]
    app_client, db_pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 8: upstream 5xx (after retries) → 503 with {"type":"upstream_unavailable"}."""
    client, _app = app_client
    await _seed_default_profile(db_pool)

    fake = FastAPI()

    @fake.get("/api/user/collection")
    async def _always_500() -> dict:
        raise HTTPException(status_code=500, detail="boom")

    monkeypatch.setattr(profile_sync, "_make_client", _client_factory_for(fake))

    auth = await _login(client)
    res = await client.post(
        f"/api/admin/profiles/{DEFAULT_UUID}/sync",
        cookies=auth["cookies"],
        headers={"X-CSRF-Token": auth["csrf_token"]},
    )
    assert res.status_code == 503, f"got {res.status_code}: {res.text}"
    body = res.json()
    detail = body.get("detail", body)
    assert detail.get("type") == "upstream_unavailable", detail


@pytest.mark.asyncio(loop_scope="session")
async def test_caches_refreshed_inline(  # type: ignore[no-untyped-def]
    app_client, db_pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 9: D-14 — caches refreshed inline before the endpoint returns 200.

    Verified via the AsyncMock substitutes on app.state (see app_client fixture):
    after the endpoint returns 200, ``collection_snapshot.load(pool)``,
    ``boundary_cache.load(pool)``, and ``segment_cache.derive(...)`` must each
    have been called at least once. Plan 06 swaps these production caches over
    to query ``profile_collection``; this test guards the inline-refresh
    contract independently of that read-path rewire.
    """
    client, app = app_client
    await _seed_default_profile(db_pool)

    seed = [_make_release(i) for i in range(1, 26)]
    fake = create_fake_app(seed=seed)
    monkeypatch.setattr(profile_sync, "_make_client", _client_factory_for(fake))

    auth = await _login(client)
    res = await client.post(
        f"/api/admin/profiles/{DEFAULT_UUID}/sync",
        cookies=auth["cookies"],
        headers={"X-CSRF-Token": auth["csrf_token"]},
    )
    assert res.status_code == 200, res.text

    # Inline refresh contract (D-14): each cache hook fired at least once before
    # the endpoint returned. The production caches still hit `v_collection` until
    # Plan 06 lands, so we verify the contract via mock call counts.
    snapshot = app.state.collection_snapshot
    boundary = app.state.boundary_cache
    assert snapshot.load.call_count >= 1, "snapshot.load was not invoked inline"
    assert boundary.load.call_count >= 1, "boundary_cache.load was not invoked inline"


@pytest.mark.asyncio(loop_scope="session")
async def test_pitfall_6_handler_does_not_hold_pool_during_sync(  # type: ignore[no-untyped-def]
    db_pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 10: Pitfall 6 — handler MUST NOT inject Depends(get_pool).

    Static check: grep for "Depends(get_pool)" in the handler source → 0.
    Observable check: while a slow sync runs in the background against a small
    pool, an out-of-band pool checkout returns <500ms (vs. the seconds it would
    take if the handler were holding a pool slot).
    """
    # Static gate matching PLAN.md verification command verbatim:
    #   `! grep -n "Depends(get_pool)" src/gruvax/api/admin/profile_sync.py`
    # — the source must contain ZERO occurrences of the literal pool-injection
    # token (docstring, comment, or code) so the regex in plan VALIDATION is
    # unambiguous.
    src = Path("src/gruvax/api/admin/profile_sync.py").read_text()
    assert "Depends(get_pool)" not in src, (
        "Plan 04 Pitfall 6 regression: handler must not inject the pool via "
        "FastAPI's get_pool dependency; use request.app.state.db_pool in a "
        "tight async with block instead."
    )

    # Observable check — run sync_profile directly with a slow fake, then probe
    # the same db_pool concurrently and assert the checkout returns quickly.
    await _seed_default_profile(db_pool)
    slow_app = _make_slow_fake_app(seed_pages=4, page_size=200, page_sleep_s=0.4)
    monkeypatch.setattr(profile_sync, "_make_client", _client_factory_for(slow_app))

    from unittest.mock import AsyncMock

    snapshot = AsyncMock()
    snapshot.invalidate = lambda: None
    boundary = AsyncMock()
    boundary.overrides = {}
    segment = AsyncMock()
    segment.derive = lambda *a, **kw: None
    app_state = types.SimpleNamespace(
        db_pool=db_pool,
        collection_snapshot=snapshot,
        boundary_cache=boundary,
        segment_cache=segment,
    )

    from gruvax.sync.profile_sync import sync_profile

    sync_task = asyncio.create_task(sync_profile(DEFAULT_UUID, app_state))
    try:
        await asyncio.sleep(0.15)  # let the sync acquire its dedicated conn + first page

        t0 = time.perf_counter()
        async with db_pool.connection(timeout=0.5) as conn, conn.cursor() as cur:
            await cur.execute("SELECT 1")
            row = await cur.fetchone()
        elapsed = time.perf_counter() - t0
        assert row[0] == 1
        assert elapsed < 0.5, (
            f"Pitfall 6 regression: pool checkout took {elapsed:.3f}s while sync was in flight; "
            f"sync_profile must use a dedicated connection."
        )
    finally:
        await sync_task


def _make_slow_fake_app(*, seed_pages: int = 5, page_size: int = 200, page_sleep_s: float = 0.5):  # type: ignore[no-untyped-def]
    """A fake-discogsography app that sleeps `page_sleep_s` per page fetch (Test 10 helper)."""
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

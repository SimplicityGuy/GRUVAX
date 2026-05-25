"""Integration tests for wizard + reshuffle commit flows (ADMN-04, ADMN-10).

Wave-0 RED scaffold — authored before the wizard endpoint exists.
Tests that target not-yet-built endpoints assert on expected status codes
so that an unimplemented endpoint (404) fails the assertion (not skips).

Tests:
  - test_wizard_atomic_commit: cubes/bulk with source='wizard' returns one change_set_id
    shared across all history rows (D-10 atomicity)
  - test_source_label: boundary_history.source='wizard' after a wizard bulk commit (D-04)
  - test_reshuffle_source: source='reshuffle' is recorded in boundary_history (D-04)
  - test_idempotency_replay: same Idempotency-Key replay → cached response, no dup history
    row (SC2, Pitfall 7)
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from gruvax.app import create_app


@pytest_asyncio.fixture(scope="module")
async def client(db_pool):  # type: ignore[no-untyped-def]
    """Module-scoped async test client with full ASGI lifespan."""
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac,
    ):
        yield ac


async def _login(client) -> dict:  # type: ignore[no-untyped-def]
    """Helper: log in and return cookies + csrf token dict."""
    res = await client.post("/api/admin/login", json={"pin": "0000"})
    if res.status_code != 200:
        return {}
    return {
        "cookies": res.cookies,
        "csrf_token": res.cookies.get("gruvax_csrf") or "",
    }


@pytest.mark.asyncio(loop_scope="session")
async def test_wizard_atomic_commit(client, four_cube_boundaries) -> None:  # type: ignore[no-untyped-def]
    """POST /api/admin/cubes/bulk with source='wizard' returns one change_set_id.

    All cubes in a single wizard commit share one change_set_id (D-10).
    Asserts on 200 so an unimplemented source-rejection path fails RED.
    """
    auth = await _login(client)
    if not auth:
        pytest.skip("Login not implemented — skipping wizard atomic commit test")

    idempotency_key = str(uuid.uuid4())
    response = await client.post(
        "/api/admin/cubes/bulk",
        json={
            "updates": [
                {
                    "unit_id": b["unit_id"],
                    "row": b["row"],
                    "col": b["col"],
                    "first_label": b["first_label"],
                    "first_catalog": b["first_catalog"],
                    "is_empty": b["is_empty"],
                    "force": True,
                }
                for b in four_cube_boundaries
            ],
            "source": "wizard",
        },
        cookies=auth["cookies"],
        headers={
            "X-CSRF-Token": auth["csrf_token"],
            "Idempotency-Key": idempotency_key,
        },
    )
    assert response.status_code == 200, (
        f"Expected 200 from cubes/bulk, got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert "change_set_id" in body, f"Response missing change_set_id: {body}"
    assert "applied" in body, f"Response missing applied count: {body}"


@pytest.mark.asyncio(loop_scope="session")
async def test_source_label(client, four_cube_boundaries, db_pool) -> None:  # type: ignore[no-untyped-def]
    """boundary_history.source='wizard' after a wizard bulk commit.

    After POST /api/admin/cubes/bulk with source='wizard', every
    boundary_history row for that change_set_id must have source='wizard' (D-04).
    """
    auth = await _login(client)
    if not auth:
        pytest.skip("Login not implemented — skipping source label test")

    idempotency_key = str(uuid.uuid4())
    response = await client.post(
        "/api/admin/cubes/bulk",
        json={
            "updates": [
                {
                    "unit_id": b["unit_id"],
                    "row": b["row"],
                    "col": b["col"],
                    "first_label": b["first_label"],
                    "first_catalog": b["first_catalog"],
                    "is_empty": b["is_empty"],
                    "force": True,
                }
                for b in four_cube_boundaries
            ],
            "source": "wizard",
        },
        cookies=auth["cookies"],
        headers={
            "X-CSRF-Token": auth["csrf_token"],
            "Idempotency-Key": idempotency_key,
        },
    )
    assert response.status_code == 200, (
        f"Expected 200 from cubes/bulk, got {response.status_code}: {response.text}"
    )
    change_set_id = response.json()["change_set_id"]

    # Verify boundary_history rows have source='wizard'
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT DISTINCT source FROM gruvax.boundary_history WHERE change_set_id = %s",
            (change_set_id,),
        )
        rows = await cur.fetchall()

    assert rows, f"No history rows found for change_set_id {change_set_id}"
    sources = {r[0] for r in rows}
    assert sources == {"wizard"}, f"Expected source='wizard' in boundary_history, got: {sources}"


@pytest.mark.asyncio(loop_scope="session")
async def test_reshuffle_source(client, four_cube_boundaries, db_pool) -> None:  # type: ignore[no-untyped-def]
    """source='reshuffle' is recorded in boundary_history after a reshuffle commit (D-04)."""
    auth = await _login(client)
    if not auth:
        pytest.skip("Login not implemented — skipping reshuffle source test")

    idempotency_key = str(uuid.uuid4())
    response = await client.post(
        "/api/admin/cubes/bulk",
        json={
            "updates": [
                {
                    "unit_id": b["unit_id"],
                    "row": b["row"],
                    "col": b["col"],
                    "first_label": b["first_label"],
                    "first_catalog": b["first_catalog"],
                    "is_empty": b["is_empty"],
                    "force": True,
                }
                for b in four_cube_boundaries
            ],
            "source": "reshuffle",
        },
        cookies=auth["cookies"],
        headers={
            "X-CSRF-Token": auth["csrf_token"],
            "Idempotency-Key": idempotency_key,
        },
    )
    assert response.status_code == 200, (
        f"Expected 200 from cubes/bulk, got {response.status_code}: {response.text}"
    )
    change_set_id = response.json()["change_set_id"]

    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT DISTINCT source FROM gruvax.boundary_history WHERE change_set_id = %s",
            (change_set_id,),
        )
        rows = await cur.fetchall()

    assert rows, f"No history rows found for change_set_id {change_set_id}"
    sources = {r[0] for r in rows}
    assert sources == {"reshuffle"}, (
        f"Expected source='reshuffle' in boundary_history, got: {sources}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_idempotency_replay(client, four_cube_boundaries, db_pool) -> None:  # type: ignore[no-untyped-def]
    """Same Idempotency-Key replay returns cached response, no duplicate history rows (SC2).

    On second POST with the same Idempotency-Key the server must return the cached
    response body without writing any new boundary_history rows (Pitfall 7).
    """
    auth = await _login(client)
    if not auth:
        pytest.skip("Login not implemented — skipping idempotency replay test")

    idempotency_key = str(uuid.uuid4())
    payload = {
        "updates": [
            {
                "unit_id": b["unit_id"],
                "row": b["row"],
                "col": b["col"],
                "first_label": b["first_label"],
                "first_catalog": b["first_catalog"],
                "is_empty": b["is_empty"],
                "force": True,
            }
            for b in four_cube_boundaries
        ],
        "source": "wizard",
    }
    headers = {
        "X-CSRF-Token": auth["csrf_token"],
        "Idempotency-Key": idempotency_key,
    }

    # First request — should commit
    r1 = await client.post(
        "/api/admin/cubes/bulk",
        json=payload,
        cookies=auth["cookies"],
        headers=headers,
    )
    assert r1.status_code == 200, f"First request failed: {r1.status_code}: {r1.text}"
    change_set_id = r1.json()["change_set_id"]

    # Count history rows after first commit
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT COUNT(*) FROM gruvax.boundary_history WHERE change_set_id = %s",
            (change_set_id,),
        )
        count_after_first = (await cur.fetchone())[0]  # type: ignore[index]

    # Second request — same Idempotency-Key, must return cached response
    r2 = await client.post(
        "/api/admin/cubes/bulk",
        json=payload,
        cookies=auth["cookies"],
        headers=headers,
    )
    assert r2.status_code == 200, f"Replay request failed: {r2.status_code}: {r2.text}"
    assert r2.json()["change_set_id"] == change_set_id, (
        "Replay returned a different change_set_id — idempotency broken"
    )

    # History row count must not increase on replay
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT COUNT(*) FROM gruvax.boundary_history WHERE change_set_id = %s",
            (change_set_id,),
        )
        count_after_replay = (await cur.fetchone())[0]  # type: ignore[index]

    assert count_after_replay == count_after_first, (
        f"Idempotency replay wrote duplicate history rows: "
        f"{count_after_first} → {count_after_replay}"
    )

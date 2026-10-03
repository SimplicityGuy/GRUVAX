"""Real preview/commit requests load one profile identity set, only when needed."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from psycopg import AsyncCursor
import pytest

from gruvax.app import create_app
from tests.cookies import cookie_header
from tests.integration.db.test_boundary_identity import (
    clear_profile,
    client as client,
    profile as profile,
)


async def seed_batch(db_pool: Any, profile: str) -> list[dict[str, Any]]:
    await clear_profile(db_pool, profile)
    edits = [
        {
            "unit_id": 1 + i // 16,
            "row": i % 16 // 4,
            "col": i % 4,
            "first_label": "STRASSE RECORDS",
            "first_catalog": f"cat-{i + 1:03}",
        }
        for i in range(32)
    ]
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.executemany(
            "INSERT INTO gruvax.profile_collection"
            " (profile_id, release_id, folder_id, label, catalog_number)"
            " VALUES (%s::uuid, %s, 1, 'Straße Records', %s)",
            [(profile, 920000 + i, f"CAT {i + 1}") for i in range(32)],
        )
        await cur.executemany(
            "INSERT INTO gruvax.cube_boundaries"
            " (profile_id,unit_id,row,col,is_empty) VALUES (%s::uuid,%s,%s,%s,TRUE)",
            [(profile, edit["unit_id"], edit["row"], edit["col"]) for edit in edits],
        )
        await conn.commit()
    return edits


async def count_empty_state(db_pool: Any, profile: str, empty: bool) -> int:
    async with db_pool.connection() as conn:
        result = await conn.execute(
            "SELECT COUNT(*) FROM gruvax.cube_boundaries WHERE profile_id=%s::uuid AND is_empty=%s",
            (profile, empty),
        )
        row = await result.fetchone()
        assert row is not None
        return int(row[0])


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("endpoint", ["validate", "bulk"])
@pytest.mark.parametrize("mode", ["normal", "force", "empty", "phantom"])
async def test_batch_identity_fetches_once_and_skips_unneeded_queries(
    db_pool: Any,
    profile: str,
    admin_session: dict[str, Any],
    monkeypatch: Any,
    endpoint: str,
    mode: str,
) -> None:
    edits = await seed_batch(db_pool, profile)
    for edit in edits:
        edit["force"] = mode == "force"
        edit["is_empty"] = mode == "empty"
    if mode == "phantom":
        edits[-1]["first_catalog"] = "MISSING 999"
    cookies = dict(admin_session["cookies"])
    cookies["gruvax_browse_binding"] = profile
    headers = {
        "X-CSRF-Token": admin_session["csrf_token"],
        "Idempotency-Key": str(uuid4()),
        **cookie_header(cookies),
    }
    collection_reads: list[str] = []
    execute = AsyncCursor.execute

    async def tracked(cursor: Any, query: Any, *args: Any, **kwargs: Any) -> Any:
        if "FROM gruvax.profile_collection" in str(query):
            collection_reads.append(str(query))
        return await execute(cursor, query, *args, **kwargs)

    # A fresh real lifespan loads the just-seeded profile's caches before spying.
    async with (
        LifespanManager(create_app()) as manager,
        AsyncClient(transport=ASGITransport(app=manager.app), base_url="http://test") as ac,
    ):
        monkeypatch.setattr(AsyncCursor, "execute", tracked)
        response = await ac.post(
            f"/api/admin/cubes/{endpoint}", headers=headers, json={"updates": edits}
        )
        expected_status = 400 if endpoint == "bulk" and mode == "phantom" else 200
        assert response.status_code == expected_status, response.text
        # A phantom additionally runs the existing near-miss suggestion query.
        expected_reads = {"normal": 1, "force": 0, "empty": 0, "phantom": 2}
        assert len(collection_reads) == expected_reads[mode]
        identity_reads = [
            read
            for read in collection_reads
            if " ".join(read.split()).startswith(
                "SELECT label, catalog_number FROM gruvax.profile_collection"
            )
        ]
        assert len(identity_reads) == (1 if mode in {"normal", "phantom"} else 0)
        if endpoint == "validate":
            assert response.json()["valid"] is (mode != "phantom")
            assert len(response.json()["results"]) == 32
        else:
            if mode == "phantom":
                assert response.json()["type"] == "phantom_boundary"
            else:
                assert response.json()["applied"] == 32
            assert await count_empty_state(db_pool, profile, mode in {"empty", "phantom"}) == 32

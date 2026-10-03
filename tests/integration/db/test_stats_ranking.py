"""Ranking must limit distinct releases after ordering by lifetime popularity."""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from gruvax.api.admin.diagnostics import router
from gruvax.api.deps import get_pool, require_admin
from gruvax.db.queries import get_top_searched
from tests.fixtures.migration_databases import (
    migration_db as migration_db,
    migration_pool as migration_pool,
)
from tests.integration.db.test_stats_windows import DEFAULT, OTHER, stats_pool as stats_pool


pytestmark = pytest.mark.asyncio(loop_scope="session")


async def seed_ranked_records(pool):  # type: ignore[no-untyped-def]
    """Twelve default releases, a duplicate folder and tempting other-profile rows."""
    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.profiles(id,display_name,app_token_encrypted) VALUES (%s,'Other ranking owner',%s)",
            (OTHER, b""),
        )
        for release_id in range(100, 112):
            count = 500 if release_id == 111 else 20
            await conn.execute(
                "INSERT INTO gruvax.profile_collection(profile_id,release_id,folder_id,title,artist) VALUES (%s,%s,2,%s,'Default artist'),(%s,%s,1,'Other profile title','Other artist')",
                (DEFAULT, release_id, f"Default {release_id}", OTHER, release_id),
            )
            await conn.execute(
                "INSERT INTO gruvax.record_stats(profile_id,release_id,search_count) VALUES (%s,%s,%s),(%s,%s,999)",
                (DEFAULT, release_id, count, OTHER, release_id),
            )
        await conn.execute(
            "INSERT INTO gruvax.profile_collection(profile_id,release_id,folder_id,title,artist) VALUES (%s,111,1,'Preferred folder title','Preferred artist')",
            (DEFAULT,),
        )
        await conn.commit()


async def test_top_n_limits_after_deduplication_and_popularity_order(stats_pool):  # type: ignore[no-untyped-def]
    await seed_ranked_records(stats_pool)
    expected_ids = [111, *range(100, 109)]
    first = await get_top_searched(stats_pool, limit=10)
    second = await get_top_searched(stats_pool, limit=10)
    assert [row["release_id"] for row in first] == expected_ids
    assert second == first
    assert [row["search_count"] for row in first] == [500, *([20] * 9)]
    assert (first[0]["title"], first[0]["primary_artist"]) == (
        "Preferred folder title",
        "Preferred artist",
    )
    assert all(row["search_count_7d"] == 0 for row in first)
    limited = await get_top_searched(stats_pool, limit=1)
    assert limited == first[:1]
    other = await get_top_searched(stats_pool, limit=3, profile_id=OTHER)
    assert [row["release_id"] for row in other] == [100, 101, 102]
    assert all(
        row["search_count"] == 999 and row["title"] == "Other profile title" for row in other
    )


async def test_diagnostics_public_default_caller_returns_true_top_ten(stats_pool):  # type: ignore[no-untyped-def]
    await seed_ranked_records(stats_pool)
    app = FastAPI()
    app.include_router(router, prefix="/api/admin")
    app.state.db_pool = stats_pool
    app.state.sync_age_seconds = 0
    # Authentication is outside this ranking test; the real route and database
    # queries retain their default-profile caller contract.
    app.dependency_overrides[require_admin] = lambda: {"role": "admin"}
    app.dependency_overrides[get_pool] = lambda: stats_pool
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/admin/diagnostics")
    assert response.status_code == 200, response.text
    rows = response.json()["top_searched"]
    assert [row["release_id"] for row in rows] == [111, *range(100, 109)]
    assert rows[0]["search_count"] == 500
    assert rows[0]["title"] == "Preferred folder title"
    assert all(row["title"] != "Other profile title" for row in rows)

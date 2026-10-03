"""Actual timestamp history, scoped windows, atomicity and lifetime preservation."""

import asyncio

from psycopg.errors import CheckViolation, RaiseException
import pytest
import pytest_asyncio

from gruvax.db.queries import (
    get_top_searched,
    increment_search_count,
    increment_selection_count,
    reset_record_stats,
)
from tests.fixtures.migration_databases import (
    migration_db as migration_db,
    migration_pool as migration_pool,
)


DEFAULT = "00000000-0000-0000-0000-000000000001"
OTHER = "00000000-0000-0000-0000-000000000002"
pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(loop_scope="session")
async def stats_pool(migration_pool, migration_db):  # type: ignore[no-untyped-def]
    import psycopg

    expected = psycopg.conninfo.conninfo_to_dict(migration_db[0])["dbname"]
    async with migration_pool.connection() as conn:
        assert await (await conn.execute("SELECT current_database()")).fetchone() == (expected,)
        await conn.execute(
            "INSERT INTO gruvax.profile_collection(profile_id,release_id,folder_id,title,artist) VALUES (%s,42,1,'Synthetic record','Synthetic artist')",
            (DEFAULT,),
        )
        await conn.commit()
    yield migration_pool


@pytest.mark.parametrize(
    "kind,increment", [("search", increment_search_count), ("selection", increment_selection_count)]
)
async def test_daily_activity_spanning_thirty_days_is_a_seven_day_window(
    stats_pool, kind, increment
):  # type: ignore[no-untyped-def]
    for age in range(29, -1, -1):
        await increment(stats_pool, 42)
        async with stats_pool.connection() as conn:
            await conn.execute(
                "UPDATE gruvax.record_activity SET occurred_at = now() - (%s * INTERVAL '1 day') WHERE id = (SELECT max(id) FROM gruvax.record_activity)",
                (age,),
            )
            await conn.commit()
    rows = await get_top_searched(stats_pool)
    assert len(rows) == 1
    assert rows[0][f"{kind}_count"] == 30
    assert rows[0][f"{kind}_count_7d"] == 7


@pytest.mark.parametrize(
    "kind,increment", [("search", increment_search_count), ("selection", increment_selection_count)]
)
async def test_dormant_activity_decays_without_any_new_write(stats_pool, kind, increment):  # type: ignore[no-untyped-def]
    await increment(stats_pool, 42)
    await increment(stats_pool, 42)
    async with stats_pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.record_activity SET occurred_at = now() - INTERVAL '9 days'"
        )
        await conn.commit()
    rows = await get_top_searched(stats_pool)
    assert len(rows) == 1
    assert rows[0][f"{kind}_count"] == 2
    assert rows[0][f"{kind}_count_7d"] == 0


async def test_failed_event_insert_rolls_back_lifetime_increment(stats_pool):  # type: ignore[no-untyped-def]
    await increment_search_count(stats_pool, 42)
    async with stats_pool.connection() as conn:
        before = await (
            await conn.execute("SELECT to_jsonb(r) FROM gruvax.record_stats r")
        ).fetchall()
        await conn.execute(
            "ALTER TABLE gruvax.record_activity ADD CONSTRAINT reject_selection CHECK (event_kind != 'selection')"
        )
        await conn.commit()
    with pytest.raises(CheckViolation):
        await increment_selection_count(stats_pool, 42)
    async with stats_pool.connection() as conn:
        assert (
            await (await conn.execute("SELECT to_jsonb(r) FROM gruvax.record_stats r")).fetchall()
            == before
        )
        assert await (
            await conn.execute("SELECT event_kind FROM gruvax.record_activity")
        ).fetchall() == [("search",)]


async def test_failed_reset_keeps_counters_and_history_together(stats_pool):  # type: ignore[no-untyped-def]
    await increment_search_count(stats_pool, 42)
    async with stats_pool.connection() as conn:
        before_stats = await (
            await conn.execute("SELECT to_jsonb(r) FROM gruvax.record_stats r")
        ).fetchall()
        before_events = await (
            await conn.execute("SELECT to_jsonb(r) FROM gruvax.record_activity r")
        ).fetchall()
        await conn.execute(
            "CREATE FUNCTION gruvax.reject_history_reset() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RAISE EXCEPTION 'synthetic history reset failure'; END$$"
        )
        await conn.execute(
            "CREATE TRIGGER reject_history_reset BEFORE TRUNCATE ON gruvax.record_activity FOR EACH STATEMENT EXECUTE FUNCTION gruvax.reject_history_reset()"
        )
        await conn.commit()
    with pytest.raises(RaiseException, match="synthetic history reset failure"):
        await reset_record_stats(stats_pool)
    async with stats_pool.connection() as conn:
        assert (
            await (await conn.execute("SELECT to_jsonb(r) FROM gruvax.record_stats r")).fetchall()
            == before_stats
        )
        assert (
            await (
                await conn.execute("SELECT to_jsonb(r) FROM gruvax.record_activity r")
            ).fetchall()
            == before_events
        )


async def test_profile_rows_and_events_do_not_mix(stats_pool):  # type: ignore[no-untyped-def]
    async with stats_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.profiles(id,display_name,app_token_encrypted) VALUES (%s,'Other stats owner',%s)",
            (OTHER, b""),
        )
        await conn.execute(
            "INSERT INTO gruvax.profile_collection(profile_id,release_id,folder_id,title,artist) VALUES (%s,42,1,'Other owned title','Other artist')",
            (OTHER,),
        )
        await conn.commit()
    await increment_search_count(stats_pool, 42)
    await increment_selection_count(stats_pool, 42, profile_id=OTHER)
    default = await get_top_searched(stats_pool, profile_id=DEFAULT)
    other = await get_top_searched(stats_pool, profile_id=OTHER)
    assert len(default) == len(other) == 1
    assert (default[0]["search_count"], default[0]["selection_count_7d"], default[0]["title"]) == (
        1,
        0,
        "Synthetic record",
    )
    assert (other[0]["search_count_7d"], other[0]["selection_count"], other[0]["title"]) == (
        0,
        1,
        "Other owned title",
    )
    await reset_record_stats(stats_pool)
    async with stats_pool.connection() as conn:
        assert await (
            await conn.execute("SELECT count(*) FROM gruvax.record_stats")
        ).fetchone() == (0,)
        assert await (
            await conn.execute("SELECT count(*) FROM gruvax.record_activity")
        ).fetchone() == (0,)


async def test_concurrent_writes_preserve_every_lifetime_increment_and_event(stats_pool):  # type: ignore[no-untyped-def]
    await asyncio.gather(*(increment_search_count(stats_pool, 42) for _ in range(20)))
    rows = await get_top_searched(stats_pool)
    assert len(rows) == 1
    assert rows[0]["search_count"] == rows[0]["search_count_7d"] == 20
    async with stats_pool.connection() as conn:
        assert await (
            await conn.execute("SELECT count(*) FROM gruvax.record_activity")
        ).fetchone() == (20,)


async def test_old_lifetime_totals_are_not_fabricated_as_recent_events(stats_pool):  # type: ignore[no-untyped-def]
    async with stats_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.record_stats(profile_id,release_id,search_count,search_count_7d,last_searched_at) VALUES (%s,42,100,100,now())",
            (DEFAULT,),
        )
        await conn.commit()
    rows = await get_top_searched(stats_pool)
    assert len(rows) == 1
    assert rows[0]["search_count"] == 100
    assert rows[0]["search_count_7d"] == 0
    async with stats_pool.connection() as conn:
        assert await (
            await conn.execute("SELECT count(*) FROM gruvax.record_activity")
        ).fetchone() == (0,)


async def test_only_expired_history_in_the_active_profile_is_pruned(stats_pool):  # type: ignore[no-untyped-def]
    async with stats_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.profiles(id,display_name,app_token_encrypted) VALUES (%s,'Retained stats owner',%s)",
            (OTHER, b""),
        )
        await conn.execute(
            "INSERT INTO gruvax.record_activity(profile_id,release_id,event_kind,occurred_at) VALUES (%s,42,'search',now()-INTERVAL '9 days'),(%s,42,'selection',now()-INTERVAL '9 days'),(%s,99,'search',now())",
            (DEFAULT, OTHER, DEFAULT),
        )
        await conn.commit()
    await increment_search_count(stats_pool, 42)
    async with stats_pool.connection() as conn:
        rows = await (
            await conn.execute(
                "SELECT profile_id::text,release_id,event_kind FROM gruvax.record_activity ORDER BY profile_id,release_id"
            )
        ).fetchall()
        assert rows == [(DEFAULT, 42, "search"), (DEFAULT, 99, "search"), (OTHER, 42, "selection")]
        columns = await (
            await conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema='gruvax' AND table_name='record_activity'"
            )
        ).fetchall()
        assert {r[0] for r in columns} == {
            "id",
            "profile_id",
            "release_id",
            "event_kind",
            "occurred_at",
        }

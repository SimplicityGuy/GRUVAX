"""Integration tests for soft-delete purge sweep — Phase 4 Plan 04-00 Task 3.

Phase 4 Wave 0 RED scaffolding (SYN-02 / D4-11..D4-14).

All three tests are RED until Plan 04-01 implements:
  - gruvax.sync.nightly._startup_purge_sweep() (or equivalent exported symbol)
  - The purge DELETE: "DELETE FROM gruvax.profile_collection WHERE profile_id = %s::uuid"

FK-SAFETY FACT (verified from migration 0009, lines 113-153 and D4-13 CONTEXT note):
  No `change_log` or `change_sets` tables exist in the gruvax schema — they were
  considered but not shipped (see migration 0009 RECONCILED note lines 158-169 and
  CONTEXT.md D4-13 commentary). Nothing REFERENCES `profile_collection` in any FK
  direction. The purge DELETE therefore has zero audit-cascade risk. The only
  tables that profile_collection relates to are:
    - gruvax.profiles (profile_id FK ON DELETE CASCADE — purge owns this direction)
  The seven v1 user-data tables (admin_sessions, boundary_history, cube_boundaries,
  idempotency_keys, record_stats, segment_overrides, settings) reference profiles.id
  but not profile_collection at all.

Behaviors under test:
  (1) test_purge_clears_profile_collection — D4-12: seed a soft-deleted profile with
      profile_collection rows; run _startup_purge_sweep; assert rows are zero afterward
      and a second sweep is a no-op (idempotent).
  (2) test_purge_audit_lineage_untouched — D4-13: purge removes ONLY profile_collection
      rows; boundary_history, cube_boundaries, segment_overrides, record_stats, settings
      rows for the soft-deleted profile survive.
  (3) test_rotate_clears_revoked — D4-09: set app_token_revoked=TRUE; perform rotate-PAT
      via in-process fake-discogsography; assert app_token_revoked is FALSE afterward.

Uses: db_pool (session-scoped), %s parameterized SQL (no f-strings), advisory-lock
awareness from test_sync_profile.py pattern, direct psycopg for row-count assertions.
"""

from __future__ import annotations

import os
import types
import uuid
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax._internal.fake_discogsography import create_fake_app
from gruvax.discogsography.client import DiscogsographyClient
from gruvax.settings import settings
from gruvax.sync import profile_sync
from gruvax.sync.pat_crypto import encrypt_pat


if TYPE_CHECKING:
    from collections.abc import AsyncIterator


# ── constants ─────────────────────────────────────────────────────────────────

_DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"
_TEST_PAT = "dscg_test_pat_PURGE_TEST_secret_bbb"
_TEST_PIN = "0000"


# ── helpers ───────────────────────────────────────────────────────────────────


def _conninfo() -> str:
    return settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)


async def _seed_soft_deleted_profile_with_collection(db_pool, profile_id: str) -> None:
    """Seed a soft-deleted profile with profile_collection rows.

    Creates profile rows + N profile_collection rows (3 synthetic releases).
    The profile has deleted_at set so it matches the purge sweep predicate.
    Uses parameterized %s SQL (no f-strings — project convention).
    """
    # Ensure profile row exists (INSERT OR UPDATE for idempotency)
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.profiles "
            "(id, display_name, app_token_encrypted, app_token_revoked, deleted_at) "
            "VALUES (%s::uuid, 'PurgeTestProfile', %s::bytea, TRUE, now()) "
            "ON CONFLICT (id) DO UPDATE SET "
            "  deleted_at = now(), "
            "  display_name = EXCLUDED.display_name",
            (profile_id, b""),
        )
        # Seed 3 profile_collection rows for this profile
        for release_id in (9901, 9902, 9903):
            await conn.execute(
                "INSERT INTO gruvax.profile_collection "
                "(profile_id, release_id, folder_id, artist, title, label, catalog_number, year) "
                "VALUES (%s::uuid, %s, 1, 'TestArtist', 'TestTitle', 'TestLabel', %s, 2000) "
                "ON CONFLICT (profile_id, release_id, folder_id) DO NOTHING",
                (profile_id, release_id, f"TEST-{release_id:04d}"),
            )
        await conn.commit()


async def _count_profile_collection_rows(db_pool, profile_id: str) -> int:
    """Count profile_collection rows for the given profile_id."""
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT COUNT(*) FROM gruvax.profile_collection WHERE profile_id = %s::uuid",
            (profile_id,),
        )
        row = await cur.fetchone()
    return row[0] if row else 0


async def _count_audit_rows(db_pool, profile_id: str) -> dict[str, int]:
    """Count per-profile rows in audit/config tables that must survive purge.

    Tables: boundary_history, cube_boundaries, segment_overrides, record_stats, settings.
    Returns a dict of table → count.

    Each query is a fully-literal SQL string (no f-strings, no concatenation) to
    satisfy bandit B608 / semgrep SQL-injection scan. The table names come from a
    closed hardcoded tuple, but the scanner cannot prove that statically, so we
    write each query out longhand.
    """
    counts: dict[str, int] = {}

    _QUERIES = {
        "boundary_history": (
            "SELECT COUNT(*) FROM gruvax.boundary_history WHERE profile_id = %s::uuid"
        ),
        "cube_boundaries": (
            "SELECT COUNT(*) FROM gruvax.cube_boundaries WHERE profile_id = %s::uuid"
        ),
        "segment_overrides": (
            "SELECT COUNT(*) FROM gruvax.segment_overrides WHERE profile_id = %s::uuid"
        ),
        "record_stats": (
            "SELECT COUNT(*) FROM gruvax.record_stats WHERE profile_id = %s::uuid"
        ),
        "settings": (
            "SELECT COUNT(*) FROM gruvax.settings WHERE profile_id = %s::uuid"
        ),
    }

    for table, sql in _QUERIES.items():
        async with db_pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(sql, (profile_id,))
            row = await cur.fetchone()
        counts[table] = row[0] if row else 0
    return counts


def _make_app_state(db_pool) -> types.SimpleNamespace:
    """Build a minimal app_state with per-profile registry mocks.

    Mirrors test_sync_profile.py _make_app_state — satisfies sync_profile's
    _refresh_profile_caches attribute access pattern without real cache plumbing.
    """
    from gruvax.events.bus import EventBus

    snapshot = AsyncMock()
    snapshot.invalidate = lambda: None
    boundary = AsyncMock()
    boundary.invalidate = lambda: None
    segment = AsyncMock()
    segment.derive = lambda *a, **kw: None
    boundary.overrides = {}
    bus = EventBus()
    return types.SimpleNamespace(
        db_pool=db_pool,
        boundary_cache_registry={_DEFAULT_PROFILE_UUID: boundary},
        snapshot_registry={_DEFAULT_PROFILE_UUID: snapshot},
        segment_cache_registry={_DEFAULT_PROFILE_UUID: segment},
        event_bus_registry={_DEFAULT_PROFILE_UUID: bus},
    )


# ── (1) Purge self-clearing predicate ─────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_purge_clears_profile_collection(db_pool) -> None:  # type: ignore[no-untyped-def]
    """Startup purge sweep removes profile_collection rows for soft-deleted profiles.

    D4-12: Sweep predicate = deleted_at IS NOT NULL AND profile_collection rows exist.
    After the sweep:
      - profile_collection rows for the soft-deleted profile are zero
      - A second sweep is a no-op (idempotent — predicate no longer matches)

    RED until Plan 04-01 implements gruvax.sync.nightly._startup_purge_sweep().
    """
    from gruvax.sync.nightly import _startup_purge_sweep

    purge_profile_id = "00000000-0000-0000-0000-000000000099"

    # Seed: soft-deleted profile with 3 profile_collection rows
    await _seed_soft_deleted_profile_with_collection(db_pool, purge_profile_id)

    # Pre-condition: rows exist
    pre_count = await _count_profile_collection_rows(db_pool, purge_profile_id)
    assert pre_count == 3, (
        f"Pre-condition failed: expected 3 profile_collection rows for {purge_profile_id}, "
        f"got {pre_count}"
    )

    # Run the startup purge sweep
    await _startup_purge_sweep(pool=db_pool)

    # Post-condition: rows are gone
    post_count = await _count_profile_collection_rows(db_pool, purge_profile_id)
    assert post_count == 0, (
        f"After _startup_purge_sweep, expected 0 profile_collection rows for "
        f"soft-deleted profile {purge_profile_id}, got {post_count}. "
        f"D4-12: sweep predicate must clear all profile_collection rows."
    )

    # Idempotency: second sweep is a no-op
    await _startup_purge_sweep(pool=db_pool)
    post2_count = await _count_profile_collection_rows(db_pool, purge_profile_id)
    assert post2_count == 0, (
        f"Second sweep should be idempotent (0 rows already gone). Got {post2_count}."
    )


# ── (2) Audit lineage untouched ───────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_purge_audit_lineage_untouched(db_pool) -> None:  # type: ignore[no-untyped-def]
    """Purge removes profile_collection ONLY; audit/config tables survive.

    D4-13: The purge DELETE is targeted at gruvax.profile_collection only.
    boundary_history, cube_boundaries, segment_overrides, record_stats, settings
    rows for the soft-deleted profile must be unchanged after the sweep.

    D4-14: The profile row itself (with deleted_at set) must still exist after
    the purge — never hard-deleted.

    FK-SAFETY FACT: No change_log/change_sets tables exist (migration 0009 RECONCILED note);
    nothing references profile_collection. Purge has zero audit-cascade risk.

    RED until Plan 04-01 implements gruvax.sync.nightly._startup_purge_sweep().
    """
    from gruvax.sync.nightly import _startup_purge_sweep

    purge_profile_id = "00000000-0000-0000-0000-000000000098"

    # Seed soft-deleted profile + 3 profile_collection rows
    await _seed_soft_deleted_profile_with_collection(db_pool, purge_profile_id)

    # Capture audit-lineage row counts BEFORE purge
    pre_audit_counts = await _count_audit_rows(db_pool, purge_profile_id)

    # Run purge sweep
    await _startup_purge_sweep(pool=db_pool)

    # profile_collection rows gone
    post_collection_count = await _count_profile_collection_rows(db_pool, purge_profile_id)
    assert post_collection_count == 0, (
        f"After purge, profile_collection must be empty for {purge_profile_id}. "
        f"Got {post_collection_count} rows."
    )

    # Audit/config tables must be unchanged
    post_audit_counts = await _count_audit_rows(db_pool, purge_profile_id)
    for table, pre_count in pre_audit_counts.items():
        post_count = post_audit_counts[table]
        assert post_count == pre_count, (
            f"After purge, gruvax.{table} rows for profile {purge_profile_id} "
            f"changed: before={pre_count}, after={post_count}. "
            f"D4-13: purge must only remove profile_collection rows."
        )

    # Profile row must still exist (D4-14 — never hard-deleted)
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id, deleted_at FROM gruvax.profiles WHERE id = %s::uuid",
            (purge_profile_id,),
        )
        profile_row = await cur.fetchone()
    assert profile_row is not None, (
        f"Profile row {purge_profile_id} was hard-deleted by purge — "
        f"D4-14 forbids hard-deleting the profile row in v2.0."
    )
    assert profile_row[1] is not None, (
        f"Profile row {purge_profile_id} had deleted_at cleared by purge — "
        f"only profile_collection rows should be removed."
    )


# ── (3) rotate-PAT clears revoked flag ────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_rotate_clears_revoked(db_pool) -> None:  # type: ignore[no-untyped-def]
    """Rotate-PAT + successful test-sync resets app_token_revoked to FALSE.

    D4-09: app_token_revoked=TRUE resets on successful rotate+sync. Badge and
    kiosk banner auto-clear on the next list/session read.

    This test verifies the already-wired reset path in rotate_pat (profiles.py
    lines 565-577 — confirmed in RESEARCH.md line 13). The integration harness
    here is new to Phase 4.

    Uses the in-process fake-discogsography (conftest._patch_make_client_with_in_process_fake
    is session-scoped autouse, so rotate routes through the in-process fake automatically).

    RED: the integration test harness for test_rotate_clears_revoked is new. The
    underlying reset code path is verified existing but this test's fixture setup
    (dedicated revoked profile seed + full ASGI rotate flow) lands in Wave 0.
    """
    from asgi_lifespan import LifespanManager

    from gruvax.app import create_app
    from gruvax.auth.pin import hash_pin

    if not os.environ.get("SESSION_SECRET"):
        os.environ["SESSION_SECRET"] = "test-session-secret-for-pytest-only"

    # Seed a second profile with app_token_revoked=TRUE for this test
    # (avoids touching the default profile which other tests rely on)
    test_profile_id: str | None = None

    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO gruvax.profiles "
            "(display_name, app_token_encrypted, app_token_revoked, last_sync_status) "
            "VALUES ('RotateTestProfile', %s::bytea, TRUE, NULL) "
            "RETURNING id::text",
            (encrypt_pat(_TEST_PAT),),
        )
        row = await cur.fetchone()
        await conn.commit()

    assert row is not None, "Rotate test profile INSERT failed"
    test_profile_id = row[0]

    try:
        # Build ASGI app with full lifespan + seeded PIN
        test_hash = hash_pin(_TEST_PIN)
        app = create_app()

        async with (
            LifespanManager(app) as manager,
            AsyncClient(
                transport=ASGITransport(app=manager.app),
                base_url="http://test",
            ) as client,
        ):
            pool = manager.app.state.db_pool

            # Seed PIN
            async with pool.connection() as conn:
                await conn.execute(
                    "INSERT INTO gruvax.settings "
                    "(profile_id, key, value, description, updated_at) "
                    "VALUES (%s::uuid, 'auth.pin_hash', %s::jsonb, "
                    "'Test PIN for test_rotate_clears_revoked', now()) "
                    "ON CONFLICT (profile_id, key) DO UPDATE "
                    "  SET value = EXCLUDED.value, updated_at = now()",
                    (_DEFAULT_PROFILE_UUID, f'"{test_hash}"'),
                )
                await conn.commit()

            # Log in
            from gruvax.api.admin.limiter import limiter
            limiter.reset()
            login_res = await client.post("/api/admin/login", json={"pin": _TEST_PIN})
            assert login_res.status_code == 200, (
                f"test_rotate_clears_revoked: login failed {login_res.status_code}: {login_res.text}"
            )
            csrf = login_res.cookies.get("gruvax_csrf") or login_res.json().get("csrf_token")
            admin_cookies = login_res.cookies

            # Confirm profile is revoked before rotate
            async with pool.connection() as conn, conn.cursor() as cur:
                await cur.execute(
                    "SELECT app_token_revoked FROM gruvax.profiles WHERE id = %s::uuid",
                    (test_profile_id,),
                )
                pre_row = await cur.fetchone()
            assert pre_row is not None, f"Test profile {test_profile_id} not found"
            assert pre_row[0] is True, (
                f"Pre-condition: app_token_revoked must be TRUE before rotate. "
                f"Got: {pre_row[0]!r}"
            )

            # Rotate PAT
            rotate_res = await client.post(
                f"/api/admin/profiles/{test_profile_id}/rotate",
                json={"pat": _TEST_PAT},
                cookies=admin_cookies,
                headers={"X-CSRF-Token": csrf},
            )
            assert rotate_res.status_code == 200, (
                f"POST /api/admin/profiles/{test_profile_id}/rotate "
                f"expected 200, got {rotate_res.status_code}: {rotate_res.text}"
            )

            # Verify app_token_revoked is now FALSE
            async with pool.connection() as conn, conn.cursor() as cur:
                await cur.execute(
                    "SELECT app_token_revoked FROM gruvax.profiles WHERE id = %s::uuid",
                    (test_profile_id,),
                )
                post_row = await cur.fetchone()
            assert post_row is not None, f"Profile {test_profile_id} not found after rotate"
            assert post_row[0] is False, (
                f"D4-09: app_token_revoked must be FALSE after successful rotate+sync. "
                f"Got: {post_row[0]!r}. "
                f"The rotate_pat handler must SET app_token_revoked = FALSE in its UPDATE."
            )

    finally:
        # Cleanup: soft-delete the test profile
        async with db_pool.connection() as conn:
            if test_profile_id is not None:
                await conn.execute(
                    "UPDATE gruvax.profiles SET deleted_at = now() "
                    "WHERE id = %s::uuid AND deleted_at IS NULL",
                    (test_profile_id,),
                )
            await conn.commit()

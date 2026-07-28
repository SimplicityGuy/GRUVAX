"""Behavioural tests for 06-01 profile-scoped writes (DATA-01) — gruvax-rh7 rewrite.

What changed and why (gruvax-rh7)
---------------------------------
This module used to verify DATA-01 by reading source text:
``assert "profile_id = %s" in inspect.getsource(queries.write_boundary)``. Source
containing the right characters is fully compatible with the bug it claimed to
exclude — a callsite passing ``profile_id=DEFAULT_PROFILE_UUID``, or a correctly
scoped write followed one line later by a default-profile cache reload, satisfies
every one of those greps. The filed default-profile bug family was green under
this suite.

The SQL-text assertions are replaced with tests that execute the queries against
two real profiles and assert on the rows: what changed, what did not, and what the
rowcount was. The remaining ``inspect.signature`` checks are kept deliberately, but
only as CHEAP TRIPWIRES for the WR-03 "profile_id is required" contract — they are
no longer the DATA-01 verification of record.

DATA-01 verification of record:
  - ``tests/integration/test_nondefault_profile_scoping.py`` — end-to-end, binding
    to profiles that are NOT the default (the case that can actually detect a
    hardcoded-default write).
  - the behavioural query-level tests in this module (below).
"""

from __future__ import annotations

import inspect
from typing import Any
import uuid

import pytest

from gruvax.api.deps import get_write_target
from gruvax.db.queries import fetch_current_boundary, write_boundary
from tests.cookies import cookie_header


DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"

# Coordinate the fixture seeds for both scratch profiles.
UNIT, ROW, COL = 1, 0, 0

# A coordinate deliberately NOT seeded for profile W — used to prove a scoped write
# to a missing row reports 0 rows rather than silently hitting another profile's row.
ABSENT_UNIT, ABSENT_ROW, ABSENT_COL = 1, 3, 3


# ── contract tripwires (cheap; NOT the DATA-01 verification of record) ─────────


class TestWriteContractTripwires:
    """Signature-level guards for the WR-03 required-profile_id contract.

    These are tripwires, not verification: a signature says nothing about which
    profile a write actually reaches. They earn their place only because the
    corresponding behaviour (ValueError on a None profile_id) is asserted below.
    """

    def test_write_boundary_accepts_profile_id(self) -> None:
        assert "profile_id" in inspect.signature(write_boundary).parameters

    def test_fetch_current_boundary_accepts_profile_id(self) -> None:
        assert "profile_id" in inspect.signature(fetch_current_boundary).parameters

    def test_write_boundary_returns_rowcount(self) -> None:
        """write_boundary must return int (rowcount), which the D-10 0-row 404 needs."""
        import typing

        hints = typing.get_type_hints(write_boundary)
        assert hints.get("return") is int, (
            "write_boundary must be annotated to return int (rowcount) — the "
            "boundary_not_found 404 path depends on the count, not on an exception"
        )

    def test_get_write_target_is_an_async_dep_taking_request(self) -> None:
        assert inspect.iscoroutinefunction(get_write_target)
        assert "request" in inspect.signature(get_write_target).parameters


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def scratch_profiles(db_pool) -> Any:  # type: ignore[no-untyped-def]
    """Create two scratch profiles (V and W), each with a boundary row at (1,0,0).

    Neither is the default profile: a write scoped to V must be observable as
    "V changed, W unchanged, DEFAULT unchanged". Function-scoped so each test
    starts from the seeded sentinels.
    """
    import psycopg

    from gruvax.settings import settings

    dsn = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    v_id = str(uuid.uuid4())
    w_id = str(uuid.uuid4())

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for pid, name in ((v_id, "WriteScopeV"), (w_id, "WriteScopeW")):
            cur.execute(
                "INSERT INTO gruvax.profiles (id, display_name, app_token_encrypted,"
                " app_token_revoked) VALUES (%s::uuid, %s, %s::bytea, TRUE)",
                (pid, name, b""),
            )
            cur.execute(
                "INSERT INTO gruvax.cube_boundaries"
                " (profile_id, unit_id, row, col, first_label, first_catalog, is_empty)"
                " VALUES (%s::uuid, %s, %s, %s, %s, %s, FALSE)",
                (pid, UNIT, ROW, COL, f"{name}-LABEL", f"{name}-001"),
            )
        conn.commit()

    yield {"v": v_id, "w": w_id}

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        # Profile delete cascades to cube_boundaries / boundary_history.
        cur.execute("DELETE FROM gruvax.profiles WHERE id = ANY(%s::uuid[])", ([v_id, w_id],))
        conn.commit()


async def _read_label(db_pool: Any, profile_id: str) -> Any:
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT first_label FROM gruvax.cube_boundaries"
            " WHERE profile_id = %s::uuid AND unit_id = %s AND row = %s AND col = %s",
            (profile_id, UNIT, ROW, COL),
        )
        got = await cur.fetchone()
        return got[0] if got else None


# ── behaviour: write_boundary ─────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_write_boundary_updates_only_the_named_profile(db_pool, scratch_profiles) -> None:  # type: ignore[no-untyped-def]
    """The WHERE clause is verified by its EFFECT, not by grepping for its text.

    Replaces ``assert "profile_id = %s" in src``: that assertion passes for SQL
    whose parameter is a hardcoded default, and for a WHERE clause that is present
    but wrong. This one fails unless exactly one profile's row moved.
    """
    v, w = scratch_profiles["v"], scratch_profiles["w"]
    w_before = await _read_label(db_pool, w)
    default_before = await _read_label(db_pool, DEFAULT_PROFILE_UUID)

    async with db_pool.connection() as conn:
        rowcount = await write_boundary(
            conn,
            UNIT,
            ROW,
            COL,
            "V-REWRITTEN",
            "V-REWRITTEN-001",
            False,
            profile_id=v,
        )
        await conn.commit()

    assert rowcount == 1, f"scoped write must affect exactly one row, got {rowcount}"
    assert await _read_label(db_pool, v) == "V-REWRITTEN", "the write did not land on profile V"
    assert await _read_label(db_pool, w) == w_before, (
        f"DATA-01 VIOLATED: profile W's row changed to {await _read_label(db_pool, w)!r} "
        f"during a write scoped to profile V"
    )
    assert await _read_label(db_pool, DEFAULT_PROFILE_UUID) == default_before, (
        "DATA-01 VIOLATED: the DEFAULT profile's row changed during a write scoped to V — "
        "this is the hardcoded-default write class the old source-grep could not see"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_write_boundary_reports_zero_rows_for_a_row_this_profile_lacks(
    db_pool,  # type: ignore[no-untyped-def]
    scratch_profiles,
) -> None:
    """A scoped write to a coordinate this profile has no row at must affect 0 rows.

    This is what makes the D-10 boundary_not_found 404 correct, and it is the
    counter-evidence to "the WHERE clause might be matching some other profile's
    row": the default profile DOES have a row at (1,3,3), so an unscoped UPDATE
    would report 1.
    """
    v = scratch_profiles["v"]
    default_before = await _read_label(db_pool, DEFAULT_PROFILE_UUID)

    async with db_pool.connection() as conn:
        rowcount = await write_boundary(
            conn,
            ABSENT_UNIT,
            ABSENT_ROW,
            ABSENT_COL,
            "SHOULD-NOT-LAND",
            "SHOULD-NOT-LAND-001",
            False,
            profile_id=v,
        )
        await conn.commit()

    assert rowcount == 0, (
        f"expected 0 rows for a coordinate profile V has no row at, got {rowcount} — "
        f"the UPDATE reached another profile's row"
    )
    assert await _read_label(db_pool, DEFAULT_PROFILE_UUID) == default_before, (
        "the default profile's row moved during a 0-row write scoped to another profile"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_write_boundary_refuses_a_missing_profile_id(db_pool) -> None:  # type: ignore[no-untyped-def]
    """WR-03: profile_id=None raises rather than writing across every profile."""
    async with db_pool.connection() as conn:
        with pytest.raises(ValueError, match="profile_id is required"):
            await write_boundary(conn, UNIT, ROW, COL, "X", "Y", False)


# ── behaviour: fetch_current_boundary ─────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_fetch_current_boundary_reads_the_named_profiles_row(
    db_pool,  # type: ignore[no-untyped-def]
    scratch_profiles,
) -> None:
    """The prev_* capture used by history must read the WRITING profile's row.

    If this read is unscoped, boundary_history records another profile's values as
    the "previous" state, which then makes a revert restore foreign data.
    """
    v, w = scratch_profiles["v"], scratch_profiles["w"]

    async with db_pool.connection() as conn:
        got_v = await fetch_current_boundary(conn, UNIT, ROW, COL, profile_id=v)
        got_w = await fetch_current_boundary(conn, UNIT, ROW, COL, profile_id=w)

    assert got_v is not None and got_w is not None
    assert got_v["first_label"] == "WriteScopeV-LABEL", got_v
    assert got_w["first_label"] == "WriteScopeW-LABEL", got_w
    assert got_v["first_label"] != got_w["first_label"], (
        "two profiles' rows at the same coordinate must not read back identically"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_fetch_current_boundary_refuses_a_missing_profile_id(db_pool) -> None:  # type: ignore[no-untyped-def]
    """WR-03: profile_id=None raises rather than scanning all profiles."""
    async with db_pool.connection() as conn:
        with pytest.raises(ValueError, match="profile_id is required"):
            await fetch_current_boundary(conn, UNIT, ROW, COL)


# ── behaviour: get_write_target refuses to guess ──────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_put_cube_boundary_no_session_returns_400(db_pool) -> None:  # type: ignore[no-untyped-def]
    """D-01/D-02: an admin PUT with no browse-binding is 400, never a default fallback.

    Unchanged from the original suite — this one was always behavioural.
    """
    from asgi_lifespan import LifespanManager
    from httpx import ASGITransport, AsyncClient

    from gruvax.app import create_app

    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(transport=ASGITransport(app=manager.app), base_url="http://test") as ac,
    ):
        login_res = await ac.post("/api/admin/login", json={"pin": "0000"})
        if login_res.status_code != 200:
            pytest.skip("Login not available — skipping unbound admin test")

        csrf_token = login_res.cookies.get("gruvax_csrf") or ""
        session_cookies = {
            k: v for k, v in login_res.cookies.items() if k in ("gruvax_session", "gruvax_csrf")
        }

        response = await ac.put(
            "/api/admin/cubes/1/0/0/boundary",
            json={
                "first_label": "Some Label",
                "first_catalog": "CAT-001",
                "is_empty": False,
                "force": True,
            },
            headers={"X-CSRF-Token": csrf_token, **cookie_header(session_cookies)},
        )
        assert response.status_code == 400, (
            f"Expected 400 session_unbound, got {response.status_code}: {response.text}"
        )
        detail = response.json().get("detail", {})
        if isinstance(detail, dict):
            assert detail.get("type") == "session_unbound", detail

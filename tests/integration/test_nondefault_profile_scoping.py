"""Behavioural profile-scoping tests where NEITHER profile is the default (gruvax-seh).

Why this module exists
----------------------
``test_two_profile_isolation.py`` binds profile A = DEFAULT_PROFILE_UUID at every
one of its write callsites (its ``_login`` helper sets
``gruvax_browse_binding = DEFAULT_PROFILE_UUID``). That makes its central
assertion — "the write bound to A did not touch B" — pass **by construction** for
a write path that ignores the binding and hardcodes the default profile: A *is*
the default, so hardcoding it is indistinguishable from honouring the binding.

The repo-wide sweep behind gruvax-seh found no test anywhere that wrote as a
NON-default profile and asserted the write landed on that profile AND the default
profile was untouched. Non-default bindings existed only in read-only tests or in
negative tests where the write never lands (``test_zero_row_write_returns_404``).
That blind spot is the structural explanation for how the whole filed
default-profile family (gruvax-xkc / -5dm / -0ge / -7ad) shipped green.

So: this module binds to profile **P** and **Q**, both non-default, and every
assertion is a triple:

  1. P changed to the value we wrote           (the write honoured the binding)
  2. Q unchanged                               (no cross-profile bleed)
  3. the DEFAULT profile unchanged             (no hardcoded-default write)

Assertion 3 is the one the existing suite structurally cannot make. A write that
hardcodes DEFAULT_PROFILE_UUID fails 1 and 3 here.

The read-side tests are the behavioural regression net for the fixes shipped in
this same batch — gruvax-5dm (public cube endpoints), gruvax-7ad (admin label /
catalog autocomplete) and gruvax-0ge (boundaries export) — replacing the
source-text greps called out by gruvax-rh7 with assertions on responses.

Fixture ordering (WARNING-2, same constraint as test_two_profile_isolation.py):
``profiles_pq`` is a dependency of ``live_server`` so both profiles exist before
``create_app()`` builds its per-profile cache and bus registries.

All SQL uses parameterised %s placeholders — no f-string SQL.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
from typing import Any
import uuid

import httpx
import psycopg
import pytest
import uvicorn
import yaml

from gruvax.app import create_app
from tests.cookies import cookie_header


logger = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────

BROWSE_BINDING_COOKIE = "gruvax_browse_binding"
DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"

# Two NON-default profiles. Fixed UUIDs (not gen_random_uuid()) so a failure
# message names something greppable, and both contain hex letters so any
# case-normalization defect (gruvax-kol) surfaces here too.
PROFILE_P = "0000000a-0000-0000-0000-00000000000a"
PROFILE_Q = "0000000b-0000-0000-0000-00000000000b"

# Coordinates every profile (P, Q and the default) holds a row at, so a write to
# one is only correct if the other two are untouched.
SHARED_UNIT, SHARED_ROW, SHARED_COL = 1, 0, 0

# Second shared coordinate, used by the bulk write so it cannot be confused with
# the single-cube PUT's target.
BULK_UNIT, BULK_ROW, BULK_COL = 1, 0, 1

# Per-profile sentinels. Labels are also seeded into profile_collection so the
# phantom check (which IS profile-scoped) accepts them for their own profile.
P_LABEL, P_CATALOG = "P-Sentinel Records", "PSR 1000"
Q_LABEL, Q_CATALOG = "Q-Sentinel Records", "QSR 1000"

# A second (label, catalog) that exists ONLY in P's collection — the value the
# scoped writes below install.
P_LABEL_2, P_CATALOG_2 = "P-Second Records", "PSR 2000"


# ── helpers ───────────────────────────────────────────────────────────────────


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _dsn() -> str:
    from gruvax.settings import settings

    return settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)


def _seed_profile(cur: Any, profile_id: str, name: str) -> None:
    """Insert (or undelete) a profile with a fixed UUID."""
    cur.execute(
        "INSERT INTO gruvax.profiles (id, display_name, app_token_encrypted, app_token_revoked)"
        " VALUES (%s::uuid, %s, %s::bytea, TRUE)"
        " ON CONFLICT (id) DO UPDATE SET deleted_at = NULL, display_name = EXCLUDED.display_name",
        (profile_id, name, b""),
    )


def _seed_collection_row(
    cur: Any, profile_id: str, release_id: int, label: str, catalog: str
) -> None:
    """Insert one profile_collection row so the phantom check can accept it."""
    cur.execute(
        "INSERT INTO gruvax.profile_collection"
        " (profile_id, release_id, folder_id, artist, title, label, catalog_number, year)"
        " VALUES (%s::uuid, %s, 0, %s, %s, %s, %s, 1970)"
        " ON CONFLICT (profile_id, release_id, folder_id) DO UPDATE"
        "   SET label = EXCLUDED.label, catalog_number = EXCLUDED.catalog_number",
        (profile_id, release_id, f"{label} Artist", f"{label} Title", label, catalog),
    )


def _seed_boundary(
    cur: Any, profile_id: str, unit: int, row: int, col: int, label: str, catalog: str
) -> None:
    cur.execute(
        "INSERT INTO gruvax.cube_boundaries"
        " (profile_id, unit_id, row, col, first_label, first_catalog, is_empty)"
        " VALUES (%s::uuid, %s, %s, %s, %s, %s, FALSE)"
        " ON CONFLICT (profile_id, unit_id, row, col) DO UPDATE"
        "   SET first_label = EXCLUDED.first_label,"
        "       first_catalog = EXCLUDED.first_catalog,"
        "       is_empty = FALSE,"
        "       updated_at = now()",
        (profile_id, unit, row, col, label, catalog),
    )


async def _read_boundary(db_pool: Any, profile_id: str, unit: int, row: int, col: int) -> Any:
    """Return (first_label, first_catalog) for one profile's row, or None."""
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT first_label, first_catalog FROM gruvax.cube_boundaries"
            " WHERE profile_id = %s::uuid AND unit_id = %s AND row = %s AND col = %s",
            (profile_id, unit, row, col),
        )
        return await cur.fetchone()


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def profiles_pq(db_pool) -> Any:  # type: ignore[no-untyped-def]
    """Create profiles P and Q with their own collection rows + boundary rows.

    Both are NON-default (that is the entire point of the module). Each gets:
      - one profile_collection row for its own sentinel (label, catalog), plus
        P's second pair, so profile-scoped phantom validation behaves realistically;
      - boundary rows at the two shared coordinates carrying its own sentinel.

    The DEFAULT profile's rows at those coordinates come from the standard
    fixtures/boundaries.yaml seed, so all three profiles hold the coordinate and
    "nobody else changed" is a meaningful assertion.

    Synchronous psycopg so the seed completes before the module's event loop work.
    """
    dsn = _dsn()
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        _seed_profile(cur, PROFILE_P, "ScopingTestP")
        _seed_profile(cur, PROFILE_Q, "ScopingTestQ")

        # Collection rows — distinct release_id ranges per profile.
        _seed_collection_row(cur, PROFILE_P, 900_001, P_LABEL, P_CATALOG)
        _seed_collection_row(cur, PROFILE_P, 900_002, P_LABEL_2, P_CATALOG_2)
        _seed_collection_row(cur, PROFILE_Q, 900_101, Q_LABEL, Q_CATALOG)

        # Boundary rows at both shared coordinates.
        for unit, row, col in (
            (SHARED_UNIT, SHARED_ROW, SHARED_COL),
            (BULK_UNIT, BULK_ROW, BULK_COL),
        ):
            _seed_boundary(cur, PROFILE_P, unit, row, col, P_LABEL, P_CATALOG)
            _seed_boundary(cur, PROFILE_Q, unit, row, col, Q_LABEL, Q_CATALOG)
        conn.commit()

    yield {"p": PROFILE_P, "q": PROFILE_Q}

    # Teardown: profile rows cascade to collection + boundaries + overrides.
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM gruvax.profiles WHERE id = ANY(%s::uuid[])",
            ([PROFILE_P, PROFILE_Q],),
        )
        conn.commit()


@pytest.fixture(scope="module")
def default_baseline(db_pool, profiles_pq) -> Any:  # type: ignore[no-untyped-def]
    """Snapshot the DEFAULT profile's rows at the shared coordinates, and restore them.

    Assertion 3 of every write test compares against this snapshot. Restoring on
    teardown keeps the module from perturbing the shared seed for other suites
    even if a scoping regression writes into the default profile.
    """
    dsn = _dsn()
    coords = ((SHARED_UNIT, SHARED_ROW, SHARED_COL), (BULK_UNIT, BULK_ROW, BULK_COL))
    baseline: dict[tuple[int, int, int], tuple[Any, Any, Any]] = {}
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for unit, row, col in coords:
            cur.execute(
                "SELECT first_label, first_catalog, is_empty FROM gruvax.cube_boundaries"
                " WHERE profile_id = %s::uuid AND unit_id = %s AND row = %s AND col = %s",
                (DEFAULT_PROFILE_UUID, unit, row, col),
            )
            got = cur.fetchone()
            if got is not None:
                baseline[(unit, row, col)] = (got[0], got[1], got[2])

    yield baseline

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for (unit, row, col), (label, catalog, is_empty) in baseline.items():
            cur.execute(
                "UPDATE gruvax.cube_boundaries"
                " SET first_label = %s, first_catalog = %s, is_empty = %s"
                " WHERE profile_id = %s::uuid AND unit_id = %s AND row = %s AND col = %s",
                (label, catalog, is_empty, DEFAULT_PROFILE_UUID, unit, row, col),
            )
        conn.commit()


@pytest.fixture(scope="module")
def live_server(db_pool, profiles_pq) -> Any:  # type: ignore[no-untyped-def]
    """Real uvicorn server in a background thread.

    profiles_pq is a dependency so P and Q exist before create_app() builds the
    per-profile registries (WARNING-2). Without that ordering every request bound
    to P or Q would 404 profile_not_found and the isolation assertions would pass
    vacuously.
    """
    port = _find_free_port()
    app = create_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, loop="asyncio", log_level="warning")
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 10.0
    while not server.started:
        if time.monotonic() > deadline:
            pytest.fail("uvicorn server did not start within 10s")
        time.sleep(0.05)

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=5)


async def _login(base_url: str, profile_id: str) -> dict[str, Any]:
    """Log in as admin and bind the browse cookie to ``profile_id``.

    The PIN itself is global (stored under the default profile — see
    api/admin/settings.py), which is exactly why the browse binding is the only
    thing that says WHICH profile this admin is acting on.
    """
    if not os.environ.get("SESSION_SECRET"):
        os.environ["SESSION_SECRET"] = "test-session-secret-for-pytest-only"

    from gruvax.auth.pin import hash_pin
    from gruvax.db.pool import create_pool

    pool = create_pool(min_size=1, max_size=2, open=False)
    await pool.open()
    try:
        async with pool.connection() as conn:
            await conn.execute(
                "INSERT INTO gruvax.settings (profile_id, key, value, description, updated_at)"
                " VALUES (%s::uuid, 'auth.pin_hash', %s::jsonb,"
                " 'Test PIN seeded by test_nondefault_profile_scoping', now())"
                " ON CONFLICT (profile_id, key) DO UPDATE"
                "   SET value = EXCLUDED.value, updated_at = now()",
                (DEFAULT_PROFILE_UUID, f'"{hash_pin("0000")}"'),
            )
            await conn.commit()
    finally:
        await pool.close()

    async with httpx.AsyncClient(base_url=base_url) as ac:
        res = await ac.post("/api/admin/login", json={"pin": "0000"})
        if res.status_code != 200:
            return {}
        cookies = dict(res.cookies)
        cookies[BROWSE_BINDING_COOKIE] = profile_id
        return {"cookies": cookies, "csrf_token": res.cookies.get("gruvax_csrf") or ""}


def _assert_untouched(
    rows: Any,
    who: str,
    expected_label: str,
    written_label: str,
) -> None:
    assert rows is not None, f"{who}'s boundary row vanished during a write bound elsewhere"
    assert rows[0] == expected_label, (
        f"PROFILE ISOLATION VIOLATED: {who}'s first_label is now {rows[0]!r} "
        f"(expected {expected_label!r}). A write bound to profile P must not touch it. "
        f"Seeing {written_label!r} here means the write ignored the binding."
    )


# ── WRITE: single-cube boundary PUT ───────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_boundary_put_as_nondefault_profile_lands_on_p_only(
    live_server,  # type: ignore[no-untyped-def]
    profiles_pq: dict[str, str],
    default_baseline: dict[tuple[int, int, int], tuple[Any, Any, Any]],
    db_pool,
) -> None:
    """DATA-01, inverse direction: PUT bound to P writes P — not Q, not the default.

    This is the test the isolation suite could not express. Because P is NOT the
    default profile, a handler that hardcodes DEFAULT_PROFILE_UUID fails two ways
    at once: P keeps its old value (assertion 1) and the default profile's row
    changes (assertion 3).
    """
    auth = await _login(live_server, profiles_pq["p"])
    if not auth:
        pytest.skip("Admin login not available")

    coord = (SHARED_UNIT, SHARED_ROW, SHARED_COL)
    default_before = default_baseline.get(coord)

    async with httpx.AsyncClient(base_url=live_server) as ac:
        res = await ac.put(
            f"/api/admin/cubes/{SHARED_UNIT}/{SHARED_ROW}/{SHARED_COL}/boundary",
            json={
                "first_label": P_LABEL_2,
                "first_catalog": P_CATALOG_2,
                "is_empty": False,
                "force": False,  # phantom check ON — it must validate against P
            },
            headers={"X-CSRF-Token": auth["csrf_token"], **cookie_header(auth["cookies"])},
        )

    assert res.status_code == 200, (
        f"PUT bound to non-default profile P must succeed (the (label, catalog) is in "
        f"P's own collection, so the profile-scoped phantom check should accept it). "
        f"Got {res.status_code}: {res.text}"
    )

    # 1. P changed.
    p_row = await _read_boundary(db_pool, profiles_pq["p"], *coord)
    assert p_row is not None and p_row[0] == P_LABEL_2, (
        f"The write did not land on profile P: its first_label is {p_row and p_row[0]!r}, "
        f"expected {P_LABEL_2!r}. A 200 with no change on the bound profile means the "
        f"write went somewhere else."
    )

    # 2. Q untouched.
    _assert_untouched(
        await _read_boundary(db_pool, profiles_pq["q"], *coord), "profile Q", Q_LABEL, P_LABEL_2
    )

    # 3. DEFAULT profile untouched — the assertion the A=default suite cannot make.
    if default_before is not None:
        default_after = await _read_boundary(db_pool, DEFAULT_PROFILE_UUID, *coord)
        assert default_after is not None and default_after[0] == default_before[0], (
            f"HARDCODED-DEFAULT WRITE: a write bound to profile P changed the DEFAULT "
            f"profile's row at {coord} from {default_before[0]!r} to "
            f"{default_after and default_after[0]!r}. This is the exact defect class the "
            f"A=default isolation suite passes by construction (gruvax-seh)."
        )


# ── WRITE: bulk commit ────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_bulk_write_as_nondefault_profile_lands_on_p_only(
    live_server,  # type: ignore[no-untyped-def]
    profiles_pq: dict[str, str],
    default_baseline: dict[tuple[int, int, int], tuple[Any, Any, Any]],
    db_pool,
) -> None:
    """POST /admin/cubes/bulk bound to P writes P only (same triple as the PUT)."""
    auth = await _login(live_server, profiles_pq["p"])
    if not auth:
        pytest.skip("Admin login not available")

    coord = (BULK_UNIT, BULK_ROW, BULK_COL)
    default_before = default_baseline.get(coord)

    async with httpx.AsyncClient(base_url=live_server) as ac:
        res = await ac.post(
            "/api/admin/cubes/bulk",
            json={
                "updates": [
                    {
                        "unit_id": BULK_UNIT,
                        "row": BULK_ROW,
                        "col": BULK_COL,
                        "first_label": P_LABEL_2,
                        "first_catalog": P_CATALOG_2,
                        "is_empty": False,
                        "force": True,
                    }
                ],
                "source": "bulk",
            },
            headers={
                "X-CSRF-Token": auth["csrf_token"],
                "Idempotency-Key": f"seh-bulk-{uuid.uuid4()}",
                **cookie_header(auth["cookies"]),
            },
        )

    assert res.status_code == 200, f"bulk write bound to P failed: {res.status_code} {res.text}"

    p_row = await _read_boundary(db_pool, profiles_pq["p"], *coord)
    assert p_row is not None and p_row[0] == P_LABEL_2, (
        f"bulk write did not land on profile P: got {p_row and p_row[0]!r}"
    )
    _assert_untouched(
        await _read_boundary(db_pool, profiles_pq["q"], *coord), "profile Q", Q_LABEL, P_LABEL_2
    )
    if default_before is not None:
        default_after = await _read_boundary(db_pool, DEFAULT_PROFILE_UUID, *coord)
        assert default_after is not None and default_after[0] == default_before[0], (
            f"HARDCODED-DEFAULT BULK WRITE: default profile's row at {coord} changed from "
            f"{default_before[0]!r} to {default_after and default_after[0]!r} during a bulk "
            f"write bound to profile P."
        )


# ── WRITE: segment cut PUT ────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_segment_cut_put_as_nondefault_profile_lands_on_p_only(
    live_server,  # type: ignore[no-untyped-def]
    profiles_pq: dict[str, str],
    default_baseline: dict[tuple[int, int, int], tuple[Any, Any, Any]],
    db_pool,
) -> None:
    """PUT /admin/cubes/{u}/{r}/{c}/cut bound to P writes P only.

    The third write class named by gruvax-seh. Same triple as the boundary PUT:
    P changed, Q untouched, DEFAULT untouched.
    """
    auth = await _login(live_server, profiles_pq["p"])
    if not auth:
        pytest.skip("Admin login not available")

    coord = (SHARED_UNIT, SHARED_ROW, SHARED_COL)
    default_before = default_baseline.get(coord)

    async with httpx.AsyncClient(base_url=live_server) as ac:
        res = await ac.put(
            f"/api/admin/cubes/{SHARED_UNIT}/{SHARED_ROW}/{SHARED_COL}/cut",
            json={"first_label": P_LABEL, "first_catalog": P_CATALOG, "force": True},
            headers={"X-CSRF-Token": auth["csrf_token"], **cookie_header(auth["cookies"])},
        )

    assert res.status_code == 200, f"cut PUT bound to P failed: {res.status_code} {res.text}"

    p_row = await _read_boundary(db_pool, profiles_pq["p"], *coord)
    assert p_row is not None and p_row[0] == P_LABEL, (
        f"cut PUT did not land on profile P: got {p_row and p_row[0]!r}, expected {P_LABEL!r}"
    )
    _assert_untouched(
        await _read_boundary(db_pool, profiles_pq["q"], *coord), "profile Q", Q_LABEL, P_LABEL
    )
    if default_before is not None:
        default_after = await _read_boundary(db_pool, DEFAULT_PROFILE_UUID, *coord)
        assert default_after is not None and default_after[0] == default_before[0], (
            f"HARDCODED-DEFAULT CUT WRITE: default profile's row at {coord} changed from "
            f"{default_before[0]!r} to {default_after and default_after[0]!r} during a cut "
            f"PUT bound to profile P."
        )


# ── WRITE: segment overrides ──────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_segment_overrides_as_nondefault_profile_land_on_p_only(
    live_server,  # type: ignore[no-untyped-def]
    profiles_pq: dict[str, str],
    db_pool,
) -> None:
    """POST /admin/cubes/{u}/{r}/{c}/overrides bound to P writes P's override rows only.

    CR-02's own test works at the DB layer because the override API validates the
    label against the in-app SegmentCache. This drives the real endpoint instead, so
    it also covers WHICH profile's cache the validation used — the label offered
    here exists only in P's collection.

    NOTE (cross-bead): set_bin_overrides validates the bin/labels against
    Depends(get_segment_cache), i.e. the DEFAULT profile's cache, which is the
    gruvax-xkc cache-scoping bead owned by the parallel group. Until that lands the
    endpoint can legitimately answer 404 bin_not_found / 400 phantom_override for a
    non-default profile, so those two responses are tolerated here — but a 200 that
    writes the row under the WRONG profile_id is never tolerated. That is the
    assertion this test exists for, and it holds either way.
    """
    auth = await _login(live_server, profiles_pq["p"])
    if not auth:
        pytest.skip("Admin login not available")

    async with httpx.AsyncClient(base_url=live_server) as ac:
        res = await ac.post(
            f"/api/admin/cubes/{SHARED_UNIT}/{SHARED_ROW}/{SHARED_COL}/overrides",
            json={"overrides": [{"label": P_LABEL, "fraction": 0.5}]},
            headers={
                "X-CSRF-Token": auth["csrf_token"],
                "Idempotency-Key": f"seh-ovr-{uuid.uuid4()}",
                **cookie_header(auth["cookies"]),
            },
        )

    assert res.status_code in (200, 400, 404), (
        f"unexpected status from overrides POST bound to P: {res.status_code} {res.text}"
    )

    # Whatever the outcome, no override row for this label may exist under any
    # profile other than P — that is the scoping invariant under test.
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT profile_id::text FROM gruvax.segment_overrides"
            " WHERE unit_id = %s AND row = %s AND col = %s AND label = %s",
            (SHARED_UNIT, SHARED_ROW, SHARED_COL, P_LABEL.casefold()),
        )
        owners = {r[0] for r in await cur.fetchall()}

    foreign = owners - {profiles_pq["p"]}
    assert not foreign, (
        f"CR-02 / gruvax-seh VIOLATED: an overrides POST bound to profile P created "
        f"segment_overrides rows under {sorted(foreign)}. "
        f"(DEFAULT is {DEFAULT_PROFILE_UUID} — seeing it here is the hardcoded-default write.)"
    )
    if res.status_code == 200:
        assert owners == {profiles_pq["p"]}, (
            f"overrides POST returned 200 but no row landed under profile P (owners={owners})"
        )


# ── WRITE: YAML import ────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_import_as_nondefault_profile_does_not_touch_other_profiles(
    live_server,  # type: ignore[no-untyped-def]
    profiles_pq: dict[str, str],
    default_baseline: dict[tuple[int, int, int], tuple[Any, Any, Any]],
    db_pool,
) -> None:
    """POST /admin/import/boundaries bound to P must not rewrite Q or the default.

    Import is the widest write in the app (D-09 replace-all over the full address
    space), so an unscoped import is the most destructive member of this bug class.

    The import may legitimately fail validation for a non-default profile while the
    default-cache dependency in import_.py (gruvax-xkc, parallel group) stands — a
    4xx is therefore tolerated. What is never tolerable is another profile's rows
    moving, which is what this asserts.
    """
    auth = await _login(live_server, profiles_pq["p"])
    if not auth:
        pytest.skip("Admin login not available")

    q_before = await _read_boundary(db_pool, profiles_pq["q"], SHARED_UNIT, SHARED_ROW, SHARED_COL)
    default_before = default_baseline.get((SHARED_UNIT, SHARED_ROW, SHARED_COL))

    payload = yaml.dump(
        {
            "version": "1",
            "cubes": [
                {
                    "unit_id": SHARED_UNIT,
                    "row": SHARED_ROW,
                    "col": SHARED_COL,
                    "first_label": P_LABEL_2,
                    "first_catalog": P_CATALOG_2,
                }
            ],
        }
    )

    async with httpx.AsyncClient(base_url=live_server) as ac:
        res = await ac.post(
            "/api/admin/import/boundaries",
            content=payload,
            headers={
                "Content-Type": "application/x-yaml",
                "X-CSRF-Token": auth["csrf_token"],
                "Idempotency-Key": f"seh-import-{uuid.uuid4()}",
                **cookie_header(auth["cookies"]),
            },
        )

    assert res.status_code < 500, f"import bound to P crashed: {res.status_code} {res.text}"

    if q_before is not None:
        _assert_untouched(
            await _read_boundary(db_pool, profiles_pq["q"], SHARED_UNIT, SHARED_ROW, SHARED_COL),
            "profile Q",
            q_before[0],
            P_LABEL_2,
        )
    if default_before is not None:
        default_after = await _read_boundary(
            db_pool, DEFAULT_PROFILE_UUID, SHARED_UNIT, SHARED_ROW, SHARED_COL
        )
        assert default_after is not None and default_after[0] == default_before[0], (
            f"HARDCODED-DEFAULT IMPORT: an import bound to profile P rewrote the DEFAULT "
            f"profile's row from {default_before[0]!r} to {default_after and default_after[0]!r}. "
            f"Import is a replace-all over the whole address space — this is the most "
            f"destructive form of the bug class."
        )
    if res.status_code == 200:
        p_after = await _read_boundary(
            db_pool, profiles_pq["p"], SHARED_UNIT, SHARED_ROW, SHARED_COL
        )
        assert p_after is not None and p_after[0] == P_LABEL_2, (
            f"import returned 200 but profile P's row is {p_after and p_after[0]!r}, "
            f"expected {P_LABEL_2!r} — the write went to another profile"
        )


# ── WRITE: history revert ─────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_history_revert_as_nondefault_profile_does_not_touch_other_profiles(
    live_server,  # type: ignore[no-untyped-def]
    profiles_pq: dict[str, str],
    default_baseline: dict[tuple[int, int, int], tuple[Any, Any, Any]],
    db_pool,
) -> None:
    """POST /admin/history/{change_set_id}/revert bound to P must revert P only.

    Closes the write-class list from gruvax-seh. A change set is created by a write
    bound to P, then reverted while still bound to P; Q and the default profile must
    be untouched by both halves.
    """
    auth = await _login(live_server, profiles_pq["p"])
    if not auth:
        pytest.skip("Admin login not available")

    coord = (BULK_UNIT, BULK_ROW, BULK_COL)
    default_before = default_baseline.get(coord)
    q_before = await _read_boundary(db_pool, profiles_pq["q"], *coord)

    headers = {"X-CSRF-Token": auth["csrf_token"], **cookie_header(auth["cookies"])}

    async with httpx.AsyncClient(base_url=live_server) as ac:
        # Create the change set via the bulk endpoint — it returns the change_set_id
        # (the single-cube PUT returns the updated row instead).
        write = await ac.post(
            "/api/admin/cubes/bulk",
            json={
                "updates": [
                    {
                        "unit_id": BULK_UNIT,
                        "row": BULK_ROW,
                        "col": BULK_COL,
                        "first_label": P_LABEL,
                        "first_catalog": P_CATALOG,
                        "is_empty": False,
                        "force": True,
                    }
                ],
                "source": "bulk",
            },
            headers={"Idempotency-Key": f"seh-revert-seed-{uuid.uuid4()}", **headers},
        )
        assert write.status_code == 200, (
            f"could not create a change set to revert: {write.status_code} {write.text}"
        )
        change_set_id = write.json().get("change_set_id")
        assert change_set_id, f"bulk write returned no change_set_id: {write.json()}"

        revert = await ac.post(f"/api/admin/history/{change_set_id}/revert", headers=headers)

    assert revert.status_code == 200, (
        f"revert of a change set created while bound to profile P must succeed — a 404 "
        f"change_set_not_found would mean the history lookup resolved a different profile. "
        f"Got {revert.status_code}: {revert.text}"
    )
    assert revert.json().get("reverted"), (
        f"revert reported nothing reverted, so the assertions below would be vacuous: "
        f"{revert.json()}"
    )

    if q_before is not None:
        _assert_untouched(
            await _read_boundary(db_pool, profiles_pq["q"], *coord),
            "profile Q",
            q_before[0],
            P_LABEL,
        )
    if default_before is not None:
        default_after = await _read_boundary(db_pool, DEFAULT_PROFILE_UUID, *coord)
        assert default_after is not None and default_after[0] == default_before[0], (
            f"HARDCODED-DEFAULT REVERT: reverting a change set bound to profile P changed the "
            f"DEFAULT profile's row at {coord} from {default_before[0]!r} to "
            f"{default_after and default_after[0]!r}."
        )


# ── WRITE: unbound admin must not fall back to the default profile ────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_unbound_admin_write_does_not_touch_any_profile(
    live_server,  # type: ignore[no-untyped-def]
    profiles_pq: dict[str, str],
    db_pool,
) -> None:
    """D-02: an unbound admin write is refused AND lands nowhere.

    test_two_profile_isolation asserts the 400 status. This adds the half that
    matters: verify no row moved. A handler that 400s only after writing, or that
    writes to the default profile before the guard runs, passes the status check
    and fails this one.
    """
    res = None
    async with httpx.AsyncClient(base_url=live_server) as ac:
        login = await ac.post("/api/admin/login", json={"pin": "0000"})
        if login.status_code != 200:
            pytest.skip("Admin login not available")
        session_only = {k: v for k, v in dict(login.cookies).items() if k != BROWSE_BINDING_COOKIE}
        before_p = await _read_boundary(
            db_pool, profiles_pq["p"], SHARED_UNIT, SHARED_ROW, SHARED_COL
        )
        res = await ac.put(
            f"/api/admin/cubes/{SHARED_UNIT}/{SHARED_ROW}/{SHARED_COL}/boundary",
            json={
                "first_label": "NEVER-LANDS",
                "first_catalog": "NEVER-001",
                "is_empty": False,
                "force": True,
            },
            headers={
                "X-CSRF-Token": login.cookies.get("gruvax_csrf") or "",
                **cookie_header(session_only),
            },
        )

    assert res.status_code == 400, f"Expected 400 session_unbound, got {res.status_code}"

    for who, pid in (
        ("profile P", profiles_pq["p"]),
        ("profile Q", profiles_pq["q"]),
        ("the DEFAULT profile", DEFAULT_PROFILE_UUID),
    ):
        row = await _read_boundary(db_pool, pid, SHARED_UNIT, SHARED_ROW, SHARED_COL)
        if row is not None:
            assert row[0] != "NEVER-LANDS", (
                f"A 400-rejected unbound write still landed on {who}. The guard must run "
                f"before any write, and there must be no default-profile fallback (D-02)."
            )
    assert before_p is not None  # sanity: P had a row to protect


# ── READ: public cube endpoints (gruvax-5dm regression net) ───────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_public_cubes_bulk_returns_only_the_bound_profile(
    live_server,  # type: ignore[no-untyped-def]
    profiles_pq: dict[str, str],
) -> None:
    """gruvax-5dm: GET /api/cubes bound to P shows P's grid — no dupes, no Q rows.

    Pre-fix the SELECT had no WHERE profile_id, so with three profiles holding
    boundary rows the kiosk received three rows per physical coordinate.
    """
    async with httpx.AsyncClient(base_url=live_server) as ac:
        res_p = await ac.get(
            "/api/cubes", headers=cookie_header({BROWSE_BINDING_COOKIE: profiles_pq["p"]})
        )
        res_q = await ac.get(
            "/api/cubes", headers=cookie_header({BROWSE_BINDING_COOKIE: profiles_pq["q"]})
        )

    assert res_p.status_code == 200, f"GET /api/cubes bound to P: {res_p.status_code} {res_p.text}"
    assert res_q.status_code == 200, f"GET /api/cubes bound to Q: {res_q.status_code} {res_q.text}"

    cubes_p = res_p.json()["cubes"]
    coords_p = [(c["unit_id"], c["row"], c["col"]) for c in cubes_p]
    assert len(coords_p) == len(set(coords_p)), (
        f"gruvax-5dm VIOLATED: GET /api/cubes returned duplicate coordinates "
        f"{sorted({c for c in coords_p if coords_p.count(c) > 1})} — cross-profile leakage. "
        f"The kiosk grid cannot render two conflicting cells for one cube."
    )
    # P seeded exactly two boundary rows; the default profile's 32 must not appear.
    assert len(cubes_p) == 2, (
        f"GET /api/cubes bound to P returned {len(cubes_p)} cubes; P has exactly 2 boundary "
        f"rows. A larger count means another profile's rows (the default's 32) leaked in."
    )
    assert len(res_q.json()["cubes"]) == 2, "GET /api/cubes bound to Q must show only Q's 2 rows"


@pytest.mark.asyncio(loop_scope="session")
async def test_public_single_cube_returns_the_bound_profiles_row(
    live_server,  # type: ignore[no-untyped-def]
    profiles_pq: dict[str, str],
) -> None:
    """gruvax-5dm: GET /api/cubes/{u}/{r}/{c} is deterministic per profile.

    P, Q and the default profile all hold a row at this coordinate. Pre-fix the
    query filtered on coordinates only and took fetchone() with no ORDER BY, so the
    kiosk showed whichever row the heap scan yielded first.

    P's row was rewritten by the boundary-PUT test above, so accept either P
    sentinel — the assertion that matters is "never Q's, never the default's".
    """
    async with httpx.AsyncClient(base_url=live_server) as ac:
        res_p = await ac.get(
            f"/api/cubes/{SHARED_UNIT}/{SHARED_ROW}/{SHARED_COL}",
            headers=cookie_header({BROWSE_BINDING_COOKIE: profiles_pq["p"]}),
        )
        res_q = await ac.get(
            f"/api/cubes/{SHARED_UNIT}/{SHARED_ROW}/{SHARED_COL}",
            headers=cookie_header({BROWSE_BINDING_COOKIE: profiles_pq["q"]}),
        )

    assert res_p.status_code == 200, f"bound to P: {res_p.status_code} {res_p.text}"
    assert res_q.status_code == 200, f"bound to Q: {res_q.status_code} {res_q.text}"

    label_p = res_p.json()["first_label"]
    label_q = res_q.json()["first_label"]

    assert label_p in (P_LABEL, P_LABEL_2), (
        f"gruvax-5dm VIOLATED: GET /api/cubes/{SHARED_UNIT}/{SHARED_ROW}/{SHARED_COL} bound to "
        f"P returned first_label={label_p!r}, which is not one of P's values. The kiosk was "
        f"shown another profile's cube."
    )
    assert label_q == Q_LABEL, (
        f"gruvax-5dm VIOLATED: the same coordinate bound to Q returned {label_q!r}, "
        f"expected {Q_LABEL!r}."
    )
    assert label_p != label_q, (
        "Two different profiles must not receive the same row for a coordinate they both hold"
    )


# ── READ: admin autocomplete (gruvax-7ad regression net) ──────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_label_autocomplete_offers_only_the_bound_profiles_labels(
    live_server,  # type: ignore[no-untyped-def]
    profiles_pq: dict[str, str],
) -> None:
    """gruvax-7ad: GET /admin/labels bound to P offers P's labels only.

    Pre-fix both autocomplete routes queried with the profile_id DEFAULT, so an
    admin bound to P was shown the default profile's label list — cross-profile
    disclosure, and a picker offering exactly what the profile-scoped phantom check
    would reject with 400 phantom_boundary.
    """
    auth_p = await _login(live_server, profiles_pq["p"])
    if not auth_p:
        pytest.skip("Admin login not available")
    auth_q = await _login(live_server, profiles_pq["q"])

    async with httpx.AsyncClient(base_url=live_server) as ac:
        res_p = await ac.get("/api/admin/labels", headers=cookie_header(auth_p["cookies"]))
        res_q = await ac.get("/api/admin/labels", headers=cookie_header(auth_q["cookies"]))

    assert res_p.status_code == 200, f"bound to P: {res_p.status_code} {res_p.text}"
    assert res_q.status_code == 200, f"bound to Q: {res_q.status_code} {res_q.text}"

    labels_p = {row["label"] for row in res_p.json()}
    labels_q = {row["label"] for row in res_q.json()}

    assert P_LABEL in labels_p, f"P's own label {P_LABEL!r} missing from its picker: {labels_p}"
    assert Q_LABEL not in labels_p, (
        f"gruvax-7ad VIOLATED: profile Q's label {Q_LABEL!r} appears in profile P's label "
        f"picker — cross-profile collection disclosure."
    )
    assert "Blue Note" not in labels_p, (
        f"gruvax-7ad VIOLATED: the DEFAULT profile's labels (e.g. 'Blue Note') appear in "
        f"profile P's picker, so the autocomplete is still reading the default profile. "
        f"Got: {sorted(labels_p)}"
    )
    assert Q_LABEL in labels_q and P_LABEL not in labels_q, (
        f"The inverse direction must hold too — Q's picker: {sorted(labels_q)}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_catalog_autocomplete_is_scoped_to_the_bound_profile(
    live_server,  # type: ignore[no-untyped-def]
    profiles_pq: dict[str, str],
) -> None:
    """gruvax-7ad: the catalog half of the two-step picker is scoped as well.

    Asking for a label that exists only in Q's collection while bound to P must
    return nothing — otherwise the picker hands the admin a catalog number the
    scoped phantom check will reject.
    """
    auth_p = await _login(live_server, profiles_pq["p"])
    if not auth_p:
        pytest.skip("Admin login not available")

    async with httpx.AsyncClient(base_url=live_server) as ac:
        own = await ac.get(
            f"/api/admin/labels/{P_LABEL}/catalogs", headers=cookie_header(auth_p["cookies"])
        )
        foreign = await ac.get(
            f"/api/admin/labels/{Q_LABEL}/catalogs", headers=cookie_header(auth_p["cookies"])
        )

    assert own.status_code == 200, f"{own.status_code}: {own.text}"
    assert foreign.status_code == 200, f"{foreign.status_code}: {foreign.text}"

    own_catalogs = {row["catalog_number"] for row in own.json()}
    assert P_CATALOG in own_catalogs, (
        f"P's own catalog {P_CATALOG!r} missing from its picker: {own_catalogs}"
    )
    assert foreign.json() == [], (
        f"gruvax-7ad VIOLATED: bound to P, the catalog picker returned rows for "
        f"{Q_LABEL!r} — a label present only in profile Q's collection: {foreign.json()}"
    )


# ── READ: boundaries export (gruvax-0ge regression net) ───────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_boundaries_export_contains_only_the_bound_profiles_cuts(
    live_server,  # type: ignore[no-untyped-def]
    profiles_pq: dict[str, str],
    db_pool,
) -> None:
    """gruvax-0ge: export bound to P carries P's cut points and P's overrides only.

    Pre-fix the cut points came from the DEFAULT profile's boundary cache and the
    segment_overrides SELECT had no WHERE profile_id, keying overrides on
    coordinates alone — so an admin bound to P downloaded the default profile's
    cuts fused with an arbitrary mix of every profile's override fractions.
    Re-importing that file (import IS scoped) corrupted P.
    """
    auth_p = await _login(live_server, profiles_pq["p"])
    if not auth_p:
        pytest.skip("Admin login not available")

    # Seed a distinguishable override on Q at a coordinate P also holds.
    dsn = _dsn()
    q_override_label = "Q-Override-Only"
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gruvax.segment_overrides"
            " (profile_id, unit_id, row, col, label, label_display, fraction, updated_at)"
            " VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, now())"
            " ON CONFLICT (profile_id, unit_id, row, col, label)"
            "   DO UPDATE SET fraction = EXCLUDED.fraction, updated_at = now()",
            (
                profiles_pq["q"],
                SHARED_UNIT,
                SHARED_ROW,
                SHARED_COL,
                q_override_label.casefold(),
                q_override_label,
                0.37,
            ),
        )
        conn.commit()

    async with httpx.AsyncClient(base_url=live_server) as ac:
        res = await ac.get(
            "/api/admin/export/boundaries.yaml", headers=cookie_header(auth_p["cookies"])
        )

    assert res.status_code == 200, f"export bound to P: {res.status_code} {res.text}"
    doc = yaml.safe_load(res.text)
    cubes = doc.get("cubes", [])

    coords = {(c["unit_id"], c["row"], c["col"]) for c in cubes}
    assert coords == {
        (SHARED_UNIT, SHARED_ROW, SHARED_COL),
        (BULK_UNIT, BULK_ROW, BULK_COL),
    }, (
        f"gruvax-0ge VIOLATED: the export bound to P describes {sorted(coords)}, but P holds "
        f"exactly two cubes. Extra coordinates mean the DEFAULT profile's boundary cache was "
        f"exported instead of P's."
    )

    exported_labels = {c.get("first_label") for c in cubes}
    assert Q_LABEL not in exported_labels, (
        f"gruvax-0ge VIOLATED: profile Q's cut point {Q_LABEL!r} appears in P's export"
    )

    all_override_labels = {lbl for c in cubes for lbl in (c.get("overrides") or {})}
    assert q_override_label not in all_override_labels, (
        f"gruvax-0ge VIOLATED: profile Q's override {q_override_label!r} was fused into P's "
        f"export. The segment_overrides SELECT must be scoped by profile_id — re-importing "
        f"this file would write Q's fractions into P (BAK-01 round-trip identity)."
    )

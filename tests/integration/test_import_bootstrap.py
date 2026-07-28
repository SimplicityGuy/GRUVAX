"""Regression test for gruvax-cam: import into an empty (v2 profile bootstrap) address space.

Bug: a freshly-created profile has ZERO rows in gruvax.cube_boundaries (the
only INSERT INTO gruvax.cube_boundaries in the whole tree was the CLI seeder,
hardcoded to the default profile — see seed_boundaries.py). Importing a
boundaries file for such a profile hit the ``if not all_addresses_raw:``
bootstrap branch in import_.py, which built ``all_edits`` from the file
directly — but the write loop called ``write_boundary`` (UPDATE-only), so
every cube's write affected 0 rows and the FIRST cube 404'd with
``boundary_not_found``. The dry_run preview (which never writes) reported
success, making the failure invisible until commit — the natural onboarding
flow for a new profile (create → import a backup boundaries.yaml) could never
actually succeed.

Fix: import_.py detects the empty-address-space case (``is_bootstrap_import``)
and calls the new ``upsert_boundary`` (INSERT ... ON CONFLICT DO UPDATE)
instead of the strict ``write_boundary`` for that one call site only — every
other write path (existing address space, cubes/segments/history editing)
is untouched and still 404s on a genuinely out-of-grid coordinate.

Uses only synthetic, made-up labels — no real collection CSV referenced.
"""

from __future__ import annotations

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax.app import create_app
from tests.cookies import cookie_header


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
    """Log in as admin and return cookies + CSRF token (no browse binding yet)."""
    res = await client.post("/api/admin/login", json={"pin": "0000"})
    if res.status_code != 200:
        return {}
    return {
        "cookies": dict(res.cookies),
        "csrf_token": res.cookies.get("gruvax_csrf") or "",
    }


def _make_empty_yaml(cubes: list[dict]) -> bytes:
    """Build an all-``is_empty: true`` synthetic YAML boundaries file.

    All-empty cubes need no phantom re-validation (import_.py skips the
    check entirely for ``is_empty`` edits) and can never trip the
    contiguity check (no label starts anywhere) — isolating this test to
    exactly the bootstrap-write-path bug (INSERT vs UPDATE), independent of
    validation concerns already covered elsewhere.
    """
    cube_lines = [
        f"  - unit_id: {c['unit_id']}\n    row: {c['row']}\n    col: {c['col']}\n    is_empty: true\n"
        for c in cubes
    ]
    return ('version: "1"\ncubes:\n' + "".join(cube_lines)).encode()


@pytest.mark.asyncio(loop_scope="session")
async def test_import_commit_succeeds_for_brand_new_profile(client, db_pool) -> None:  # type: ignore[no-untyped-def]
    """A freshly-created profile (zero cube_boundaries rows) can import + commit.

    Regression for gruvax-cam: before the fix, this always 404'd
    ``boundary_not_found`` on the first cube despite preview reporting success.
    """
    auth = await _login(client)
    assert auth, "Login must be available for the bootstrap import test"

    # ── 1. Create a brand-new profile — zero cube_boundaries rows anywhere ──
    create_res = await client.post(
        "/api/admin/profiles",
        json={"display_name": "Bootstrap Test Profile"},
        headers={
            "X-CSRF-Token": auth["csrf_token"],
            **cookie_header(auth["cookies"]),
        },
    )
    assert create_res.status_code in (200, 201), (
        f"profile create failed: {create_res.status_code} {create_res.text}"
    )
    profile_id = create_res.json()["id"]

    try:
        # ── 2. Bind the browse cookie to the new profile ────────────────────
        cookies = dict(auth["cookies"])
        cookies["gruvax_browse_binding"] = profile_id

        cubes = [{"unit_id": 1, "row": 0, "col": c} for c in range(4)]
        file_bytes = _make_empty_yaml(cubes)

        # ── 3. dry_run preview — this already "succeeds" even pre-fix ───────
        preview_res = await client.post(
            "/api/admin/import/boundaries",
            params={"dry_run": "true"},
            content=file_bytes,
            headers={
                "Content-Type": "application/x-yaml",
                "X-CSRF-Token": auth["csrf_token"],
                **cookie_header(cookies),
            },
        )
        assert preview_res.status_code == 200, (
            f"dry_run preview expected 200, got {preview_res.status_code}: {preview_res.text}"
        )
        preview_body = preview_res.json()
        assert preview_body["total_cubes"] == 0, (
            "brand-new profile must start with zero cube_boundaries rows"
        )
        assert preview_body["file_cube_count"] == 4

        # ── 4. Commit — this is the bug: must NOT 404 boundary_not_found ────
        import uuid

        commit_res = await client.post(
            "/api/admin/import/boundaries",
            content=file_bytes,
            headers={
                "Content-Type": "application/x-yaml",
                "X-CSRF-Token": auth["csrf_token"],
                "Idempotency-Key": str(uuid.uuid4()),
                **cookie_header(cookies),
            },
        )
        assert commit_res.status_code == 200, (
            "import commit into an empty address space must succeed (gruvax-cam); "
            f"got {commit_res.status_code}: {commit_res.text}"
        )
        body = commit_res.json()
        assert body["applied"] == 4
        assert "change_set_id" in body

        # ── 5. The rows now genuinely exist for THIS profile (DB-level proof;
        # GET /api/admin/export/boundaries.yaml is a separate, not-yet
        # profile-scoped endpoint — out of scope for gruvax-cam) ────────────
        async with db_pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*) FROM gruvax.cube_boundaries WHERE profile_id = %s::uuid",
                (profile_id,),
            )
            row = await cur.fetchone()
        assert row[0] == 4, (
            f"expected 4 cube_boundaries rows for the bootstrapped profile, got {row[0]}"
        )
    finally:
        # Deterministic DB-level cleanup: the profile DELETE cascades to its
        # cube_boundaries rows. (The admin API delete was fire-and-forget here
        # and silently left the profile behind, which then broke migration
        # 0009's downgrade-to-v1-PK in the round-trip tests — two profiles'
        # rows collide on the old (unit_id, row, col) primary key.)
        async with db_pool.connection() as conn:
            await conn.execute(
                "DELETE FROM gruvax.profiles WHERE id = %s::uuid",
                (profile_id,),
            )
            await conn.commit()

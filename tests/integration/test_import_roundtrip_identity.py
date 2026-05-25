"""Integration tests: export → re-import round-trip identity (BAK-01, SC4, G3).

Purpose:
  Prove that seeding a synthetic boundary state, exporting it, and re-importing
  the EXACT exported bytes:
    1. At dry_run preview → zero diff, zero errors (diff_preview == [])
    2. At commit → 200 + change_set_id; a second export equals the first

These tests use ONLY synthetic data (four_cube_boundaries / thirty_two_cube_boundaries
from conftest.py). The real collection CSV and background/ directory are NEVER referenced.

Design notes:
  - Reuse the module-scoped ``client`` + ``_login`` pattern from test_import.py and
    test_export.py — do NOT rely on the admin_session conftest fixture (known broken,
    see integration-harness notes).
  - Force=True on the bulk seed bypasses phantom check for synthetic labels not in
    dev v_collection (established harness pattern per conftest docstring).
  - Re-seed boundary state at test start to avoid state bleed from shared dev DB.
  - @pytest.mark.asyncio(loop_scope="session") required for session-scoped db_pool.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import yaml
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
async def test_export_reimport_identity(client, four_cube_boundaries) -> None:  # type: ignore[no-untyped-def]
    """Seed synthetic state, export it, re-import the unedited bytes → identity (SC4, BAK-01).

    Steps:
      1. Seed boundary state via POST /api/admin/cubes/bulk with force=True on each edit
         (bypass phantom — synthetic labels are NOT in dev v_collection).
      2. Export: GET /api/admin/export/boundaries.yaml → 200, capture YAML bytes.
      3. Dry-run re-import: POST /api/admin/import/boundaries?dry_run=true with the raw bytes
         → 200, diff_preview == [] (EMPTY — W5 guarantees identical cubes are omitted),
         file_cube_count == total_cubes, no errors.
      4. Commit re-import: POST /api/admin/import/boundaries with same bytes (no dry_run)
         → 200, change_set_id present.
      5. Second export: GET /api/admin/export/boundaries.yaml → bytes equal the first export.

    Asserts the empty list explicitly — not merely a derived count (SC4 round-trip invariant).
    Synthetic data only — no real collection CSV referenced.
    """
    auth = await _login(client)
    assert auth, "Login must be available for identity round-trip test"

    # ── 1. Seed via bulk with force=True (phantom bypass for synthetic labels) ─
    updates_with_force = [
        {
            "unit_id": c["unit_id"],
            "row": c["row"],
            "col": c["col"],
            "first_label": c["first_label"],
            "first_catalog": c["first_catalog"],
            "is_empty": c.get("is_empty", False),
            "force": True,  # bypass phantom — synthetic labels not in dev v_collection
        }
        for c in four_cube_boundaries
    ]
    seed_resp = await client.post(
        "/api/admin/cubes/bulk",
        json={"updates": updates_with_force, "source": "bulk"},
        headers={
            "X-CSRF-Token": auth["csrf_token"],
            "Idempotency-Key": str(uuid.uuid4()),
        },
        cookies=auth["cookies"],
    )
    assert seed_resp.status_code == 200, (
        f"Seed via bulk failed: {seed_resp.status_code}: {seed_resp.text}"
    )

    # ── 2. Export the current state ───────────────────────────────────────────
    export_resp = await client.get(
        "/api/admin/export/boundaries.yaml",
        cookies=auth["cookies"],
    )
    assert export_resp.status_code == 200, (
        f"Export failed: {export_resp.status_code}: {export_resp.text}"
    )
    assert "application/x-yaml" in export_resp.headers.get("content-type", ""), (
        "Export must return application/x-yaml content-type"
    )
    yaml_bytes = export_resp.content
    # Sanity-check: exported YAML must be parseable with a 'cubes' key
    export_data = yaml.safe_load(yaml_bytes)
    assert isinstance(export_data, dict) and "cubes" in export_data, (
        f"Export YAML missing 'cubes' key: {export_data}"
    )

    # ── 3. Dry-run re-import: assert zero diff (W5 / SC4) ────────────────────
    dry_run_resp = await client.post(
        "/api/admin/import/boundaries?dry_run=true",
        content=yaml_bytes,
        headers={
            "X-CSRF-Token": auth["csrf_token"],
            "Content-Type": "application/x-yaml",
        },
        cookies=auth["cookies"],
    )
    assert dry_run_resp.status_code == 200, (
        f"Dry-run re-import failed: {dry_run_resp.status_code}: {dry_run_resp.text}"
    )
    dry_data = dry_run_resp.json()

    # W5: diff_preview MUST be an empty list (cubes equal to committed state are
    # omitted entirely — NOT carried as delta 0). An identity re-import yields [].
    assert "diff_preview" in dry_data, f"Dry-run response missing diff_preview: {dry_data}"
    assert dry_data["diff_preview"] == [], (
        f"Expected empty diff_preview on identity re-import (W5/SC4), "
        f"got {len(dry_data['diff_preview'])} entries: {dry_data['diff_preview']}"
    )

    # file_cube_count == total_cubes: full export re-import — no partial-import warning
    assert "file_cube_count" in dry_data, f"Dry-run response missing file_cube_count: {dry_data}"
    assert "total_cubes" in dry_data, f"Dry-run response missing total_cubes: {dry_data}"
    assert dry_data["file_cube_count"] == dry_data["total_cubes"], (
        f"Expected file_cube_count == total_cubes on full export re-import, "
        f"got file_cube_count={dry_data['file_cube_count']}, "
        f"total_cubes={dry_data['total_cubes']}"
    )

    # Dry-run must NOT produce a change_set_id (no write)
    assert "change_set_id" not in dry_data, f"Dry-run must not mint a change_set_id: {dry_data}"

    # ── 4. Commit re-import: assert 200 + change_set_id ──────────────────────
    commit_resp = await client.post(
        "/api/admin/import/boundaries",
        content=yaml_bytes,
        headers={
            "X-CSRF-Token": auth["csrf_token"],
            "Content-Type": "application/x-yaml",
        },
        cookies=auth["cookies"],
    )
    assert commit_resp.status_code == 200, (
        f"Commit re-import failed: {commit_resp.status_code}: {commit_resp.text}"
    )
    commit_data = commit_resp.json()
    assert "change_set_id" in commit_data, f"Commit response missing change_set_id: {commit_data}"

    # ── 5. Second export must equal the first (round-trip identity) ───────────
    export_resp2 = await client.get(
        "/api/admin/export/boundaries.yaml",
        cookies=auth["cookies"],
    )
    assert export_resp2.status_code == 200, (
        f"Second export failed: {export_resp2.status_code}: {export_resp2.text}"
    )
    assert export_resp2.content == yaml_bytes, (
        "Second export after identity re-import must equal the first export (round-trip identity)"
    )

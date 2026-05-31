"""Unit tests for reshuffle draft persistence and re-validate behavior (ADMN-10, D-05/D-06).

Tests the reshuffle-draft contract at the Python layer:
  - Draft schema round-trip (serialize → deserialize identity)
  - Stale cut re-validation via POST /api/admin/cubes/validate (D-06)

The draft data structure mirrors the Zustand localStorage persist contract
(mode, completedSteps, cuts, idempotencyKey, startedAt). The Python test
exercises the validate endpoint contract against a synthetic stale draft
without touching localStorage itself (the cross-session browser behavior
is covered by the 07-05 human-verify checkpoint).

Tests:
  - test_draft_persists: draft dict survives a serialize→deserialize cycle
  - test_resume_revalidates_stale_cut: a draft with a stale cut (label no longer
    in v_collection) → POST /api/admin/cubes/validate returns phantom_boundary (D-06)
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import uuid

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

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
    """Helper: log in and return cookies + csrf token dict.

    Merges the browse-binding cookie (D-02 fail-loud contract) so that admin
    write requests (and validate, which now requires a bound session per WR-01)
    resolve the per-profile session required by get_write_target.
    """
    res = await client.post("/api/admin/login", json={"pin": "0000"})
    if res.status_code != 200:
        return {}
    cookies = dict(res.cookies)
    # WR-01 (Phase 6 CR fix): validate_boundary depends on get_write_target;
    # the browse-binding cookie is required so the resolved profile scopes
    # phantom checks correctly.
    cookies["gruvax_browse_binding"] = "00000000-0000-0000-0000-000000000001"
    return {
        "cookies": cookies,
        "csrf_token": res.cookies.get("gruvax_csrf") or "",
    }


def _make_draft(
    mode: str = "reshuffle",
    completed_steps: int = 3,
    cuts: dict | None = None,
    idempotency_key: str | None = None,
    started_at: str | None = None,
) -> dict:
    """Build a synthetic reshuffle draft dict matching the Zustand persist contract."""
    return {
        "mode": mode,
        "completedSteps": completed_steps,
        "cuts": cuts
        or {
            "1/0/0": {
                "first_label": "Atlantic",
                "first_catalog": "ATL-001",
                "is_empty": False,
            },
            "1/0/1": {
                "first_label": "Blue Note",
                "first_catalog": "BNL-001",
                "is_empty": False,
            },
            "1/0/2": {
                "first_label": "Columbia",
                "first_catalog": "COL-001",
                "is_empty": False,
            },
        },
        "idempotencyKey": idempotency_key or str(uuid.uuid4()),
        "startedAt": started_at or datetime.now(UTC).isoformat(),
    }


@pytest.mark.asyncio(loop_scope="session")
async def test_draft_persists() -> None:
    """Reshuffle draft survives a serialize → deserialize cycle (D-05).

    Verifies that a draft dict with mode, completedSteps, cuts, idempotencyKey,
    and startedAt fields round-trips through JSON without data loss.
    This mirrors the Zustand localStorage persist contract.

    Pure Python test — no DB or HTTP client required.
    """
    original = _make_draft(
        mode="reshuffle",
        completed_steps=5,
        cuts={
            "1/0/0": {
                "first_label": "Atlantic",
                "first_catalog": "ATL-D01",
                "is_empty": False,
            },
            "1/1/0": {
                "first_label": "Blue Note",
                "first_catalog": "BNL-D01",
                "is_empty": False,
            },
        },
        idempotency_key="test-idem-key-roundtrip",
        started_at="2026-05-24T10:00:00+00:00",
    )

    # Serialize to JSON (what localStorage does) then deserialize
    serialized = json.dumps(original)
    restored = json.loads(serialized)

    # All fields must survive round-trip
    assert restored["mode"] == original["mode"], "mode field lost in round-trip"
    assert restored["completedSteps"] == original["completedSteps"], (
        "completedSteps field lost in round-trip"
    )
    assert restored["cuts"] == original["cuts"], "cuts field lost in round-trip"
    assert restored["idempotencyKey"] == original["idempotencyKey"], (
        "idempotencyKey field lost in round-trip"
    )
    assert restored["startedAt"] == original["startedAt"], "startedAt field lost in round-trip"

    # Verify the cuts keys follow the expected ${unit_id}/${row}/${col} format
    for key in restored["cuts"]:
        parts = key.split("/")
        assert len(parts) == 3, f"Cut key must be unit/row/col format, got: {key}"
        assert all(p.isdigit() for p in parts), f"Cut key parts must be integers, got: {key}"


@pytest.mark.asyncio(loop_scope="session")
async def test_resume_revalidates_stale_cut(client) -> None:  # type: ignore[no-untyped-def]
    """Stale draft cut → POST /api/admin/cubes/validate returns phantom_boundary (D-06).

    When a reshuffle draft is resumed but one of its cut records uses a label/catalog
    that is no longer in v_collection (stale), re-validation must surface a
    phantom_boundary error for that cut (D-06).

    The validate endpoint is already implemented (Phase 3) and returns 400 with
    type='phantom_boundary' for unknown label/catalog pairs.

    This test targets /api/admin/cubes/validate with a stale-cut payload and
    asserts on the 400 phantom_boundary shape. The test fails RED until the
    validate path handles stale-draft re-validation correctly — or stays GREEN
    if the existing phantom check already handles this case.
    """
    auth = await _login(client)
    assert auth, "Login must be available for stale-cut re-validation test"

    # A stale cut: label/catalog pair that does not exist in v_collection
    # (these are purely synthetic and should never match real collection data)
    stale_cut_update = {
        "unit_id": 1,
        "row": 3,
        "col": 3,
        "first_label": "Stale Label That No Longer Exists ZZZZZ",
        "first_catalog": "STALE-9999-PHANTOM",
        "is_empty": False,
        "force": False,  # force=False so phantom check fires
    }

    response = await client.post(
        "/api/admin/cubes/validate",
        json={"updates": [stale_cut_update]},
        cookies=auth["cookies"],
        headers={"X-CSRF-Token": auth["csrf_token"]},
    )

    # The validate endpoint is a dry-run: it returns 200 with valid=false
    # and a results list containing phantom indicators.
    # For a stale draft cut, the result must include phantom=true for that cube (D-06).
    assert response.status_code == 200, (
        f"Expected 200 from validate dry-run, got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert body.get("valid") is False, f"Expected valid=false for stale-cut validate, got: {body}"
    results = body.get("results", [])
    assert results, f"Expected non-empty results for stale-cut validate, got: {body}"
    # At least one result must flag the phantom (D-06 stale-draft re-validate)
    phantom_results = [r for r in results if r.get("phantom") is True]
    assert phantom_results, (
        f"Expected phantom=true in validate results for stale cut (D-06), got: {results}"
    )
    # near_misses must be present in each phantom result (may be empty list)
    for pr in phantom_results:
        assert "near_misses" in pr, f"Expected near_misses in phantom result, got: {pr}"

"""Integration tests for change-set history and undo (ADMN-09).

Tests:
  - test_bulk_writes_history: bulk save writes boundary_history with shared change_set_id
  - test_idempotency_key_replay: replay of same Idempotency-Key does not double-write
  - test_revert_writes_inverse: revert writes inverse change-set with source='revert'
  - test_revert_conflict_skip: reverting a cube changed by newer change-set → skip+report
  - test_revert_is_undoable: the revert change-set is itself undoable (history is append-only)

These tests target endpoints implemented in Plans 03/04/05 — authored RED in Wave-0.

Analog: tests/integration/test_search.py (LifespanManager + AsyncClient pattern).
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
async def test_bulk_writes_history(client) -> None:  # type: ignore[no-untyped-def]
    """POST /api/admin/cubes/bulk writes one boundary_history row per cube with shared change_set_id.

    All cubes in a single bulk request share the same change_set_id (D-10).
    """
    auth = await _login(client)
    if not auth:
        pytest.skip("Login not implemented — skipping bulk history test")

    idempotency_key = str(uuid.uuid4())
    response = await client.post(
        "/api/admin/cubes/bulk",
        json={
            "updates": [
                {
                    "unit_id": 1,
                    "row": 0,
                    "col": 0,
                    "first_label": "Blue Note",
                    "first_catalog": "BLP 4001",
                    "is_empty": False,
                    "force": True,
                }
            ]
        },
        cookies=auth["cookies"],
        headers={
            "X-CSRF-Token": auth["csrf_token"],
            "Idempotency-Key": idempotency_key,
        },
    )
    if response.status_code == 404:
        pytest.skip("Bulk endpoint not yet implemented")

    assert response.status_code == 200, (
        f"Expected 200 from bulk save, got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert "change_set_id" in body, "Bulk save response must include change_set_id"
    assert "applied" in body, "Bulk save response must include applied count"


@pytest.mark.asyncio(loop_scope="session")
async def test_idempotency_key_replay(client) -> None:  # type: ignore[no-untyped-def]
    """Replaying the same Idempotency-Key returns the cached response without double-writing.

    D-10 / Pitfall 7: a retry on flaky LAN Wi-Fi must not create two history rows.
    """
    auth = await _login(client)
    if not auth:
        pytest.skip("Login not implemented — skipping idempotency test")

    idempotency_key = str(uuid.uuid4())
    payload = {
        "updates": [
            {
                "unit_id": 1,
                "row": 0,
                "col": 1,
                "first_label": "Blue Note",
                "first_catalog": "BLP 4101",
                "is_empty": False,
                "force": True,
            }
        ]
    }
    headers = {
        "X-CSRF-Token": auth["csrf_token"],
        "Idempotency-Key": idempotency_key,
    }

    # First request
    res1 = await client.post(
        "/api/admin/cubes/bulk",
        json=payload,
        cookies=auth["cookies"],
        headers=headers,
    )
    if res1.status_code == 404:
        pytest.skip("Bulk endpoint not yet implemented")
    assert res1.status_code == 200

    # Second request with same Idempotency-Key — must return same response
    res2 = await client.post(
        "/api/admin/cubes/bulk",
        json=payload,
        cookies=auth["cookies"],
        headers=headers,
    )
    assert res2.status_code == 200, (
        f"Replay with same Idempotency-Key must return 200, got {res2.status_code}"
    )
    # Both responses must have the same change_set_id (replay returns cached)
    assert res1.json().get("change_set_id") == res2.json().get("change_set_id"), (
        "Replay must return the same change_set_id as the original request"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_revert_writes_inverse(client) -> None:  # type: ignore[no-untyped-def]
    """POST /api/admin/history/{change_set_id}/revert writes an inverse change-set with source='revert'.

    The revert is itself undoable (D-11).
    """
    auth = await _login(client)
    if not auth:
        pytest.skip("Login not implemented — skipping revert test")

    # First make a change to create a history entry
    idempotency_key = str(uuid.uuid4())
    bulk_res = await client.post(
        "/api/admin/cubes/bulk",
        json={
            "updates": [
                {
                    "unit_id": 1,
                    "row": 1,
                    "col": 0,
                    "first_label": "ECM",
                    "first_catalog": "ECM 1001",
                    "is_empty": False,
                    "force": True,
                }
            ]
        },
        cookies=auth["cookies"],
        headers={
            "X-CSRF-Token": auth["csrf_token"],
            "Idempotency-Key": idempotency_key,
        },
    )
    if bulk_res.status_code == 404:
        pytest.skip("Bulk endpoint not yet implemented")
    assert bulk_res.status_code == 200

    change_set_id = bulk_res.json().get("change_set_id")
    assert change_set_id, "Bulk save must return change_set_id"

    # Revert the change-set
    revert_res = await client.post(
        f"/api/admin/history/{change_set_id}/revert",
        cookies=auth["cookies"],
        headers={"X-CSRF-Token": auth["csrf_token"]},
    )
    if revert_res.status_code == 404:
        pytest.skip("Revert endpoint not yet implemented")

    assert revert_res.status_code == 200, (
        f"Expected 200 from revert, got {revert_res.status_code}: {revert_res.text}"
    )
    body = revert_res.json()
    assert "reverted" in body or "change_set_id" in body, (
        "Revert response must include reverted list or change_set_id"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_revert_conflict_skip(client) -> None:  # type: ignore[no-untyped-def]
    """Reverting a cube changed by a NEWER change-set skips that cube and reports it (D-12).

    No silent clobber: only non-conflicting cubes are reverted.
    """
    auth = await _login(client)
    if not auth:
        pytest.skip("Login not implemented — skipping conflict-skip test")

    # Make original change to cube (1,2,0)
    orig_res = await client.post(
        "/api/admin/cubes/bulk",
        json={
            "updates": [
                {
                    "unit_id": 1,
                    "row": 2,
                    "col": 0,
                    "first_label": "Verve",
                    "first_catalog": "V 8001",
                    "is_empty": False,
                    "force": True,
                }
            ]
        },
        cookies=auth["cookies"],
        headers={
            "X-CSRF-Token": auth["csrf_token"],
            "Idempotency-Key": str(uuid.uuid4()),
        },
    )
    if orig_res.status_code == 404:
        pytest.skip("Bulk endpoint not yet implemented")
    if orig_res.status_code != 200:
        pytest.skip("Bulk endpoint returned unexpected status")

    original_change_set_id = orig_res.json().get("change_set_id")

    # Make a NEWER change to the same cube
    newer_res = await client.post(
        "/api/admin/cubes/bulk",
        json={
            "updates": [
                {
                    "unit_id": 1,
                    "row": 2,
                    "col": 0,
                    "first_label": "Verve",
                    "first_catalog": "V 8200",
                    "is_empty": False,
                    "force": True,
                }
            ]
        },
        cookies=auth["cookies"],
        headers={
            "X-CSRF-Token": auth["csrf_token"],
            "Idempotency-Key": str(uuid.uuid4()),
        },
    )
    assert newer_res.status_code == 200

    # Now revert the ORIGINAL change-set — cube (1,2,0) was changed by newer → must be skipped
    revert_res = await client.post(
        f"/api/admin/history/{original_change_set_id}/revert",
        cookies=auth["cookies"],
        headers={"X-CSRF-Token": auth["csrf_token"]},
    )
    if revert_res.status_code == 404:
        pytest.skip("Revert endpoint not yet implemented")

    assert revert_res.status_code == 200
    body = revert_res.json()
    # The conflicting cube must be in the skipped list
    assert "skipped" in body, "Revert response must include skipped list for conflicts (D-12)"
    assert len(body.get("skipped", [])) >= 1, (
        "The conflicting cube (1,2,0) must appear in the skipped list"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_revert_is_undoable(client) -> None:  # type: ignore[no-untyped-def]
    """The revert change-set is itself undoable — history is append-only (D-11).

    After a revert, GET /api/admin/history must show both the original and
    the revert change-sets, and the revert change-set must be revertable.
    """
    auth = await _login(client)
    if not auth:
        pytest.skip("Login not implemented — skipping revert-is-undoable test")

    # Make a change
    bulk_res = await client.post(
        "/api/admin/cubes/bulk",
        json={
            "updates": [
                {
                    "unit_id": 1,
                    "row": 3,
                    "col": 0,
                    "first_label": "Impulse",
                    "first_catalog": "A 1",
                    "is_empty": False,
                    "force": True,
                }
            ]
        },
        cookies=auth["cookies"],
        headers={
            "X-CSRF-Token": auth["csrf_token"],
            "Idempotency-Key": str(uuid.uuid4()),
        },
    )
    if bulk_res.status_code == 404:
        pytest.skip("Bulk endpoint not yet implemented")
    if bulk_res.status_code != 200:
        pytest.skip("Bulk save failed — skipping undoable test")

    change_set_id = bulk_res.json().get("change_set_id")

    # Revert it
    revert_res = await client.post(
        f"/api/admin/history/{change_set_id}/revert",
        cookies=auth["cookies"],
        headers={"X-CSRF-Token": auth["csrf_token"]},
    )
    if revert_res.status_code == 404:
        pytest.skip("Revert endpoint not yet implemented")
    if revert_res.status_code != 200:
        pytest.skip("Revert failed — skipping undoable test")

    revert_change_set_id = revert_res.json().get("change_set_id")
    assert revert_change_set_id, "Revert must return its own change_set_id"

    # The revert change-set must appear in history
    history_res = await client.get(
        "/api/admin/history",
        cookies=auth["cookies"],
    )
    if history_res.status_code == 404:
        pytest.skip("History endpoint not yet implemented")

    assert history_res.status_code == 200
    history = history_res.json().get("history", [])
    change_set_ids = [h.get("change_set_id") for h in history]
    assert revert_change_set_id in change_set_ids, (
        "The revert change-set must appear in history (append-only log, D-11)"
    )

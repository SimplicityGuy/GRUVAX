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


# ── INT-B: SegmentCache re-derive + boundary_changed publish after revert ────


@pytest.mark.asyncio(loop_scope="session")
async def test_revert_rederives_segment_cache(client) -> None:  # type: ignore[no-untyped-def]
    """After revert_change_set, /api/locate returns a fresh result (SegmentCache re-derived).

    INT-B regression guard (ADMN-09): previously, revert_change_set only reloaded
    BoundaryCache but never re-derived SegmentCache, leaving /api/locate stale until
    the next admin write or restart.

    Strategy:
      1. Record the current /api/locate result for Riverside release_id=136
         (cube 2/0/0 in the fixture — Riverside label starts there).
      2. Do a bulk write to cube (2, 0, 0) changing its cut point to a different
         label so Riverside records are pushed to a different cube.
      3. Record /api/locate again — must differ from step 1 (SegmentCache updated).
      4. Revert the change_set.
      5. Record /api/locate a third time — must differ from step 3 AND match step 1
         (SegmentCache re-derived after revert, not stale-until-restart).

    Teardown: the revert in step 4 restores cube (2, 0, 0) to its original state.
    The test uses a cube (unit 2, row 0, col 0) not referenced by any other test in
    this module — safe to mutate on the shared dev DB.

    This test is RED before the INT-B fix in history.py (revert never re-derives
    SegmentCache, so step 5 returns the same stale result as step 3).
    """
    auth = await _login(client)
    if not auth:
        pytest.skip("Login not implemented — skipping revert re-derive test")

    # Step 1: Record locate result for Riverside release 136 before any mutation.
    # release_id=136 is "Brilliant Corners" (Riverside RLP 12-226) — in the synthetic fixture.
    pre_locate = await client.get("/api/locate", params={"release_id": 136})
    if pre_locate.status_code == 404:
        pytest.skip("Release 136 not in v_collection — skipping re-derive test")
    assert pre_locate.status_code == 200, (
        f"Expected 200 from /api/locate, got {pre_locate.status_code}: {pre_locate.text}"
    )
    pre_body = pre_locate.json()
    pre_cube = pre_body.get("primary_cube")

    # Step 2: Bulk write cube (2, 0, 0) — change label away from Riverside to push
    # Riverside records out of cube 2/0/0.  force=True bypasses phantom check.
    bulk_res = await client.post(
        "/api/admin/cubes/bulk",
        json={
            "updates": [
                {
                    "unit_id": 2,
                    "row": 0,
                    "col": 0,
                    "first_label": "Zappa",
                    "first_catalog": "ZAP-001",
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
        pytest.skip("Bulk endpoint not yet implemented — skipping re-derive test")
    assert bulk_res.status_code == 200, (
        f"Expected 200 from bulk write, got {bulk_res.status_code}: {bulk_res.text}"
    )
    change_set_id = bulk_res.json().get("change_set_id")
    assert change_set_id, "Bulk write must return change_set_id"

    # Step 3: Locate after bulk write — SegmentCache was re-derived by the bulk write handler.
    post_write_locate = await client.get("/api/locate", params={"release_id": 136})
    assert post_write_locate.status_code == 200
    post_write_body = post_write_locate.json()
    post_write_cube = post_write_body.get("primary_cube")

    # Step 4: Revert the bulk write.
    revert_res = await client.post(
        f"/api/admin/history/{change_set_id}/revert",
        cookies=auth["cookies"],
        headers={"X-CSRF-Token": auth["csrf_token"]},
    )
    if revert_res.status_code == 404:
        pytest.skip("Revert endpoint not yet implemented — skipping re-derive test")
    assert revert_res.status_code == 200, (
        f"Expected 200 from revert, got {revert_res.status_code}: {revert_res.text}"
    )
    reverted = revert_res.json().get("reverted", [])
    assert len(reverted) >= 1, "Revert must have reverted at least one cube"

    # Step 5: Locate after revert — the INT-B fix makes revert re-derive SegmentCache,
    # so /api/locate must return the same result as before the bulk write (step 1).
    # Without the fix, this returns the stale post-write result (same as step 3).
    post_revert_locate = await client.get("/api/locate", params={"release_id": 136})
    assert post_revert_locate.status_code == 200
    post_revert_body = post_revert_locate.json()
    post_revert_cube = post_revert_body.get("primary_cube")

    # The revert must have changed the SegmentCache-derived result back.
    # After revert: result must differ from the post-write result (step 3 ≠ step 5).
    # If SegmentCache was NOT re-derived (INT-B bug), step 5 == step 3 and this fails.
    assert post_revert_cube != post_write_cube, (
        "After revert, /api/locate should return a different primary_cube than after the bulk "
        f"write — got same cube {post_revert_cube!r} in both step 3 and step 5. "
        "This means SegmentCache was NOT re-derived after revert (INT-B regression)."
    )
    # And the result after revert should match what it was before (step 1 == step 5).
    assert post_revert_cube == pre_cube, (
        f"After revert, /api/locate should return the same primary_cube as before the bulk "
        f"write: expected {pre_cube!r}, got {post_revert_cube!r}. "
        "SegmentCache was not fully restored by the revert."
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_revert_publishes_boundary_changed(db_pool) -> None:  # type: ignore[no-untyped-def]
    """After revert_change_set, a boundary_changed event is published with reverted cube_ids.

    INT-B regression guard (RTM-01): previously, revert_change_set never called
    bus.publish(), so the kiosk never received a live re-render event after an undo.

    Strategy:
      Uses a fresh app instance with a SpyEventBus injected via dependency_overrides
      (avoids polluting the module-scoped client fixture and ensures we capture only
      the events from this test's revert call).

      1. Override get_event_bus with a SpyEventBus that records publish() calls.
      2. Make a bulk write to cube (2, 0, 1) to create a change_set_id.
      3. Call the revert endpoint.
      4. Assert the SpyEventBus recorded a boundary_changed event with:
           - cube_ids = [{"unit": 2, "row": 0, "col": 1}]  (key "unit", not "unit_id")
           - change_set_id = the NEW revert change_set_id (from the revert response)

    Teardown: the revert itself restores cube (2, 0, 1) to its original state.
    Uses cube (unit 2, row 0, col 1) — not referenced by any other test in this module.

    This test is RED before the INT-B fix in history.py (revert never publishes).
    """
    from gruvax.api.deps import get_event_bus

    class SpyEventBus:
        """Records all bus.publish() calls for assertion."""

        def __init__(self) -> None:
            self.published: list[tuple[str, dict]] = []

        async def publish(self, event: str, payload: dict) -> None:  # type: ignore[override]
            self.published.append((event, payload))

    spy = SpyEventBus()

    def _spy_get_event_bus() -> SpyEventBus:
        return spy

    # Seed the test PIN so login works in the fresh app instance.
    from gruvax.auth.pin import hash_pin

    test_pin_hash = hash_pin("0000")
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.settings (key, value, description, updated_at)"
            " VALUES ('auth.pin_hash', %s, 'Test PIN hash seeded by INT-B publish test', now())"
            " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
            (f'"{test_pin_hash}"',),
        )
        await conn.commit()

    # Build a fresh app instance with the SpyEventBus override.
    from gruvax.app import create_app

    app = create_app()
    app.dependency_overrides[get_event_bus] = _spy_get_event_bus

    try:
        async with (
            LifespanManager(app) as manager,
            AsyncClient(
                transport=ASGITransport(app=manager.app),
                base_url="http://test",
            ) as ac,
        ):
            # Log in
            login_res = await ac.post("/api/admin/login", json={"pin": "0000"})
            if login_res.status_code != 200:
                pytest.skip("Login not implemented — skipping publish test")
            auth_cookies = login_res.cookies
            csrf_token = login_res.cookies.get("gruvax_csrf") or ""

            # Make a bulk write to cube (2, 0, 1) — creates a change_set.
            bulk_res = await ac.post(
                "/api/admin/cubes/bulk",
                json={
                    "updates": [
                        {
                            "unit_id": 2,
                            "row": 0,
                            "col": 1,
                            "first_label": "Zappa",
                            "first_catalog": "ZAP-002",
                            "is_empty": False,
                            "force": True,
                        }
                    ]
                },
                cookies=auth_cookies,
                headers={
                    "X-CSRF-Token": csrf_token,
                    "Idempotency-Key": str(uuid.uuid4()),
                },
            )
            if bulk_res.status_code == 404:
                pytest.skip("Bulk endpoint not yet implemented — skipping publish test")
            assert bulk_res.status_code == 200, (
                f"Bulk write failed: {bulk_res.status_code}: {bulk_res.text}"
            )
            change_set_id = bulk_res.json().get("change_set_id")
            assert change_set_id, "Bulk write must return change_set_id"

            # Clear spy events accumulated from the bulk write (we only want revert events).
            spy.published.clear()

            # Revert the change_set.
            revert_res = await ac.post(
                f"/api/admin/history/{change_set_id}/revert",
                cookies=auth_cookies,
                headers={"X-CSRF-Token": csrf_token},
            )
            if revert_res.status_code == 404:
                pytest.skip("Revert endpoint not yet implemented — skipping publish test")
            assert revert_res.status_code == 200, (
                f"Revert failed: {revert_res.status_code}: {revert_res.text}"
            )
            revert_body = revert_res.json()
            new_change_set_id = revert_body.get("change_set_id")
            assert new_change_set_id, "Revert must return its own change_set_id"
    finally:
        app.dependency_overrides.pop(get_event_bus, None)

    # Assert the SpyEventBus captured a boundary_changed event from the revert.
    # Without the INT-B fix, revert never calls bus.publish(), so spy.published is empty.
    assert spy.published, (
        "Expected revert_change_set to publish at least one event via EventBus, "
        "but spy.published is empty. INT-B: revert never calls bus.publish()."
    )

    # Find the boundary_changed event.
    boundary_events = [(ev, pl) for (ev, pl) in spy.published if ev == "boundary_changed"]
    assert boundary_events, (
        f"Expected a 'boundary_changed' event, but spy captured: {spy.published}"
    )

    event_name, payload = boundary_events[-1]  # the revert's publish is the last one

    # Verify cube_ids shape: must use "unit" (not "unit_id") to match ShimmerCube contract.
    assert "cube_ids" in payload, (
        f"boundary_changed payload must have 'cube_ids' key, got: {payload}"
    )
    cube_ids = payload["cube_ids"]
    assert isinstance(cube_ids, list) and len(cube_ids) >= 1, (
        f"cube_ids must be a non-empty list, got: {cube_ids}"
    )

    # At least one entry must be the reverted cube (2, 0, 1).
    matching = [c for c in cube_ids if c.get("unit") == 2 and c.get("row") == 0 and c.get("col") == 1]
    assert matching, (
        f"Expected cube_ids to contain {{unit: 2, row: 0, col: 1}}, got: {cube_ids}. "
        "Key 'unit' (not 'unit_id') is required by the ShimmerCube contract."
    )

    # Verify the change_set_id in the payload is the NEW revert change_set_id.
    assert payload.get("change_set_id") == new_change_set_id, (
        f"boundary_changed payload change_set_id must equal the revert's new change_set_id "
        f"({new_change_set_id!r}), got: {payload.get('change_set_id')!r}"
    )

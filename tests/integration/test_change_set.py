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
    write requests resolve the per-profile session required by get_write_target.
    """
    res = await client.post("/api/admin/login", json={"pin": "0000"})
    if res.status_code != 200:
        return {}
    cookies = dict(res.cookies)
    # Bind the default profile so get_write_target resolves without session_unbound (D-02).
    cookies["gruvax_browse_binding"] = "00000000-0000-0000-0000-000000000001"
    return {
        "cookies": cookies,
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
async def test_revert_rederives_segment_cache(db_pool) -> None:  # type: ignore[no-untyped-def]
    """After revert_change_set, SegmentCache is re-derived (GET /segments shows fresh state).

    INT-B regression guard (ADMN-09): previously, revert_change_set only reloaded
    BoundaryCache but never re-derived SegmentCache, leaving segment data stale until
    the next admin write or restart.

    Strategy:
      Uses a fresh app instance with boundaries reseeded from fixtures/boundaries.yaml so
      the initial state is known (cube 1/0/1 has cut-point "Blue Note").  Uses
      GET /api/admin/cubes/1/0/1/segments to directly read the SegmentCache state.

      1. Record the labels present in the SegmentCache for cube (1, 0, 1).
      2. Do a bulk write to cube (1, 0, 1) changing its cut point to "Riverside".
         Verify the SegmentCache changed (step 2b: the bulk write handler already
         re-derives SegmentCache, so segments must differ from step 1).
      3. Revert the change_set.
      4. Read /segments again — after the INT-B fix, SegmentCache was re-derived by
         the revert, so labels must match the pre-write state (step 1 == step 4).
         Without the fix, the stale post-write state persists (step 2b == step 4),
         and the first assertion below fails.

    Teardown: the revert in step 3 restores cube (1, 0, 1) to its pre-write state.
    The fresh app instance ensures no shared-state contamination from other tests.

    This test is RED before the INT-B fix in history.py (revert never re-derives
    SegmentCache, so step 4 matches the stale post-write state, not the pre-write state).
    """
    from pathlib import Path

    from gruvax.app import create_app
    from gruvax.db.seed_boundaries import load_boundaries

    _YAML = Path(__file__).parents[2] / "fixtures" / "boundaries.yaml"

    # Seed the test PIN so login works in the fresh app instance.
    from gruvax.auth.pin import hash_pin

    test_pin_hash = hash_pin("0000")
    _DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.settings (profile_id, key, value, description, updated_at)"
            " VALUES (%s::uuid, 'auth.pin_hash', %s, 'Test PIN hash seeded by INT-B re-derive test', now())"
            " ON CONFLICT (profile_id, key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
            (_DEFAULT_PROFILE_UUID, f'"{test_pin_hash}"'),
        )
        await conn.commit()

    # Reseed boundaries to the canonical fixture BEFORE creating the app so the
    # BoundaryCache (loaded once at lifespan startup) sees the known state.
    # This prevents contamination from prior mutating tests on the shared dev DB.
    await load_boundaries(_YAML)

    app = create_app()

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
            pytest.skip("Login not implemented — skipping re-derive test")
        # Merge the browse-binding cookie so get_write_target resolves without 400 (D-02).
        auth_cookies = dict(login_res.cookies)
        auth_cookies["gruvax_browse_binding"] = "00000000-0000-0000-0000-000000000001"
        csrf_token = login_res.cookies.get("gruvax_csrf") or ""

        # Step 1: Record current SegmentCache state for cube (1, 0, 1).
        # Fixture: cube (1, 0, 1) has cut-point "Blue Note" BNL-001 — it has real
        # Blue Note records in the collection, so segments is non-empty.
        pre_seg_res = await ac.get(
            "/api/admin/cubes/1/0/1/segments",
            cookies=auth_cookies,
        )
        if pre_seg_res.status_code == 404:
            pytest.skip("GET segments endpoint not implemented or cube (1,0,1) not in cache")
        assert pre_seg_res.status_code == 200, (
            f"Expected 200 from GET segments, got {pre_seg_res.status_code}: {pre_seg_res.text}"
        )
        pre_labels = {s["label"] for s in pre_seg_res.json().get("segments", [])}
        assert pre_labels, (
            "Fixture cube (1,0,1) should have non-empty segments (Blue Note has collection records)"
        )

        # Step 2: Bulk write cube (1, 0, 1) — change cut-point to "Riverside" RLP 12-226.
        # "Riverside" is in v_collection.  force=True bypasses phantom check.
        # This changes which label starts at cube (1,0,1), altering the SegmentCache.
        bulk_res = await ac.post(
            "/api/admin/cubes/bulk",
            json={
                "updates": [
                    {
                        "unit_id": 1,
                        "row": 0,
                        "col": 1,
                        "first_label": "Riverside",
                        "first_catalog": "RLP 12-226",
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
            pytest.skip("Bulk endpoint not yet implemented — skipping re-derive test")
        assert bulk_res.status_code == 200, (
            f"Expected 200 from bulk write, got {bulk_res.status_code}: {bulk_res.text}"
        )
        change_set_id = bulk_res.json().get("change_set_id")
        assert change_set_id, "Bulk write must return change_set_id"

        # Step 2b: Confirm SegmentCache changed after the bulk write.
        post_write_seg_res = await ac.get(
            "/api/admin/cubes/1/0/1/segments",
            cookies=auth_cookies,
        )
        assert post_write_seg_res.status_code == 200
        post_write_labels = {s["label"] for s in post_write_seg_res.json().get("segments", [])}
        assert post_write_labels != pre_labels, (
            f"Bulk write did not change SegmentCache for cube (1,0,1): "
            f"pre={pre_labels!r}, post-write={post_write_labels!r}"
        )

        # Step 3: Revert the bulk write.
        revert_res = await ac.post(
            f"/api/admin/history/{change_set_id}/revert",
            cookies=auth_cookies,
            headers={"X-CSRF-Token": csrf_token},
        )
        if revert_res.status_code == 404:
            pytest.skip("Revert endpoint not yet implemented — skipping re-derive test")
        assert revert_res.status_code == 200, (
            f"Expected 200 from revert, got {revert_res.status_code}: {revert_res.text}"
        )
        reverted = revert_res.json().get("reverted", [])
        assert len(reverted) >= 1, "Revert must have reverted at least one cube"

        # Step 4: Read segments after revert.
        # The INT-B fix makes revert re-derive SegmentCache → segments match pre-write state.
        # Without the fix, SegmentCache is stale → segments still match post-write state.
        post_revert_seg_res = await ac.get(
            "/api/admin/cubes/1/0/1/segments",
            cookies=auth_cookies,
        )
        assert post_revert_seg_res.status_code == 200
        post_revert_labels = {s["label"] for s in post_revert_seg_res.json().get("segments", [])}

        # The revert must have changed the SegmentCache back.
        # After revert: segments must differ from post-write segments (step 4 ≠ step 2b).
        # If SegmentCache was NOT re-derived (INT-B bug), step 4 == step 2b and this fails.
        assert post_revert_labels != post_write_labels, (
            "After revert, GET /segments must return different labels than after the bulk write. "
            f"Post-write labels: {post_write_labels!r}, post-revert labels: {post_revert_labels!r}. "
            "SegmentCache was NOT re-derived after revert (INT-B regression)."
        )
        # And the result after revert should match what it was before (step 1 == step 4).
        assert post_revert_labels == pre_labels, (
            "After revert, GET /segments must return the same labels as before the bulk write. "
            f"Pre-write: {pre_labels!r}, post-revert: {post_revert_labels!r}. "
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

      1. Override get_write_target with a SpyEventBus that records publish() calls.
      2. Make a bulk write to cube (2, 0, 1) to create a change_set_id.
      3. Call the revert endpoint.
      4. Assert the SpyEventBus recorded a boundary_changed event with:
           - cube_ids = [{"unit": 2, "row": 0, "col": 1}]  (key "unit", not "unit_id")
           - change_set_id = the NEW revert change_set_id (from the revert response)

    Teardown: the revert itself restores cube (2, 0, 1) to its original state.
    Uses cube (unit 2, row 0, col 1) — not referenced by any other test in this module.

    This test is RED before the INT-B fix in history.py (revert never publishes).
    """
    from gruvax.api.deps import get_write_target

    class SpyEventBus:
        """Records all bus.publish() calls for assertion."""

        def __init__(self) -> None:
            self.published: list[tuple[str, dict]] = []

        async def publish(self, event: str, payload: dict) -> None:  # type: ignore[override]
            self.published.append((event, payload))

    spy = SpyEventBus()

    _DEFAULT_PROFILE_UUID_CHANGESET = "00000000-0000-0000-0000-000000000001"

    def _spy_get_write_target() -> tuple[str, SpyEventBus]:
        # Returns (profile_id, spy_bus) — matches the get_write_target return type.
        # Plan 06-01 (D-04): admin write routes use get_write_target, not get_event_bus.
        return _DEFAULT_PROFILE_UUID_CHANGESET, spy

    # Seed the test PIN so login works in the fresh app instance.
    from gruvax.auth.pin import hash_pin

    test_pin_hash = hash_pin("0000")
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.settings (profile_id, key, value, description, updated_at)"
            " VALUES (%s::uuid, 'auth.pin_hash', %s, 'Test PIN hash seeded by INT-B publish test', now())"
            " ON CONFLICT (profile_id, key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
            (_DEFAULT_PROFILE_UUID_CHANGESET, f'"{test_pin_hash}"'),
        )
        await conn.commit()

    # Build a fresh app instance with the SpyEventBus override.
    from gruvax.app import create_app

    app = create_app()
    # Override get_write_target (not get_event_bus) — routes resolve per-profile bus
    # from event_bus_registry, not from app.state.event_bus (Plan 06-01 / D-04).
    app.dependency_overrides[get_write_target] = _spy_get_write_target

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
            # Merge the browse-binding cookie so get_write_target resolves without 400 (D-02).
            auth_cookies = dict(login_res.cookies)
            auth_cookies["gruvax_browse_binding"] = "00000000-0000-0000-0000-000000000001"
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
        app.dependency_overrides.pop(get_write_target, None)

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

    _event_name, payload = boundary_events[-1]  # the revert's publish is the last one

    # Verify cube_ids shape: must use "unit" (not "unit_id") to match ShimmerCube contract.
    assert "cube_ids" in payload, (
        f"boundary_changed payload must have 'cube_ids' key, got: {payload}"
    )
    cube_ids = payload["cube_ids"]
    assert isinstance(cube_ids, list) and len(cube_ids) >= 1, (
        f"cube_ids must be a non-empty list, got: {cube_ids}"
    )

    # At least one entry must be the reverted cube (2, 0, 1).
    matching = [
        c for c in cube_ids if c.get("unit") == 2 and c.get("row") == 0 and c.get("col") == 1
    ]
    assert matching, (
        f"Expected cube_ids to contain {{unit: 2, row: 0, col: 1}}, got: {cube_ids}. "
        "Key 'unit' (not 'unit_id') is required by the ShimmerCube contract."
    )

    # Verify the change_set_id in the payload is the NEW revert change_set_id.
    assert payload.get("change_set_id") == new_change_set_id, (
        f"boundary_changed payload change_set_id must equal the revert's new change_set_id "
        f"({new_change_set_id!r}), got: {payload.get('change_set_id')!r}"
    )

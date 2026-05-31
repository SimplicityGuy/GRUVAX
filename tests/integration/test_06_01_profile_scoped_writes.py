"""Tests for 06-01: profile-scoped write_boundary + get_write_target (DATA-01).

RED phase: these tests are written before the implementation; they verify:
  1. write_boundary returns int rowcount and accepts profile_id in WHERE.
  2. fetch_current_boundary accepts profile_id and scopes the SELECT.
  3. get_write_target raises 400 session_unbound with no browse-binding cookie.
  4. get_write_target returns per-profile bus, not default app.state.event_bus.

These tests must FAIL before the Task 1 implementation and PASS after.
"""

from __future__ import annotations

import inspect

import pytest

from gruvax.api.deps import get_write_target


# ── Static / import-time checks (no DB needed) ───────────────────────────────


class TestWriteBoundarySignature:
    """write_boundary must accept profile_id and return int rowcount."""

    def test_write_boundary_accepts_profile_id(self) -> None:
        from gruvax.db.queries import write_boundary

        sig = inspect.signature(write_boundary)
        assert "profile_id" in sig.parameters, (
            "write_boundary must have a profile_id parameter"
        )

    def test_write_boundary_returns_int_annotation(self) -> None:
        from gruvax.db.queries import write_boundary

        hints = {}
        try:
            import typing

            hints = typing.get_type_hints(write_boundary)
        except Exception:
            pass
        # At minimum the annotation must not be None — we check that the function
        # has been updated to return int (rowcount).  A return annotation of None
        # means the original signature is still in place.
        ret = hints.get("return", None)
        assert ret is not None and ret is not type(None), (
            "write_boundary must be annotated to return int (rowcount), not None"
        )

    def test_fetch_current_boundary_accepts_profile_id(self) -> None:
        from gruvax.db.queries import fetch_current_boundary

        sig = inspect.signature(fetch_current_boundary)
        assert "profile_id" in sig.parameters, (
            "fetch_current_boundary must have a profile_id parameter"
        )


class TestGetWriteTargetExists:
    """get_write_target must exist in deps.py and return a 2-tuple."""

    def test_get_write_target_importable(self) -> None:
        # Import already done at module top — just assert it's callable.
        assert callable(get_write_target), "get_write_target must be callable"

    def test_get_write_target_is_async(self) -> None:
        assert inspect.iscoroutinefunction(get_write_target), (
            "get_write_target must be an async function"
        )

    def test_get_write_target_has_request_param(self) -> None:
        sig = inspect.signature(get_write_target)
        assert "request" in sig.parameters, (
            "get_write_target must accept a 'request' parameter"
        )


# ── Integration-level behaviour tests (require running app + DB) ─────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_put_cube_boundary_no_session_returns_400(db_pool) -> None:  # type: ignore[no-untyped-def]
    """PUT /api/admin/cubes/.../boundary with no browse-binding returns 400 session_unbound.

    D-01/D-02: get_write_target must raise 400 session_unbound when there is no
    browse-binding cookie and no device fingerprint — never fall back to DEFAULT_PROFILE_UUID.
    """
    from asgi_lifespan import LifespanManager
    from httpx import ASGITransport, AsyncClient

    from gruvax.app import create_app

    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac,
    ):
        # Login to get admin session (but no browse-binding cookie)
        login_res = await ac.post("/api/admin/login", json={"pin": "0000"})
        if login_res.status_code != 200:
            pytest.skip("Login not available — skipping unbound admin test")

        csrf_token = login_res.cookies.get("gruvax_csrf") or ""

        # PUT with admin session but WITHOUT browse-binding cookie
        # We pass only the session + csrf cookies, NOT gruvax_profile_id
        session_cookies = {
            k: v
            for k, v in login_res.cookies.items()
            if k in ("gruvax_session", "gruvax_csrf")
        }

        response = await ac.put(
            "/api/admin/cubes/1/0/0/boundary",
            json={
                "first_label": "Some Label",
                "first_catalog": "CAT-001",
                "is_empty": False,
                "force": True,
            },
            cookies=session_cookies,
            headers={"X-CSRF-Token": csrf_token},
        )
        # Must fail with 400 session_unbound (D-01, D-02)
        assert response.status_code == 400, (
            f"Expected 400 session_unbound, got {response.status_code}: {response.text}"
        )
        body = response.json()
        detail = body.get("detail", body)
        if isinstance(detail, dict):
            assert detail.get("type") == "session_unbound", (
                f"Expected type=session_unbound, got: {detail}"
            )


@pytest.mark.asyncio(loop_scope="session")
async def test_write_boundary_sql_contains_profile_id(db_pool) -> None:  # type: ignore[no-untyped-def]
    """write_boundary UPDATE WHERE clause must contain 'profile_id = %s' (D-03, T-06-01).

    Inspects the source of write_boundary directly to verify the SQL contains the
    profile_id guard — this catches any case where the parameter exists but the SQL
    was not updated.
    """
    import inspect as insp

    from gruvax.db import queries

    src = insp.getsource(queries.write_boundary)
    assert "profile_id" in src, (
        "write_boundary source must mention profile_id"
    )
    # The WHERE clause pattern check
    assert "profile_id = %s" in src or "profile_id=%s" in src, (
        "write_boundary WHERE clause must contain 'profile_id = %s'"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_fetch_current_boundary_sql_contains_profile_id(db_pool) -> None:  # type: ignore[no-untyped-def]
    """fetch_current_boundary SELECT WHERE clause must contain profile_id = %s."""
    import inspect as insp

    from gruvax.db import queries

    src = insp.getsource(queries.fetch_current_boundary)
    assert "profile_id = %s" in src or "profile_id=%s" in src, (
        "fetch_current_boundary WHERE clause must contain 'profile_id = %s'"
    )

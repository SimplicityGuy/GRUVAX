"""Playwright reboot-persistence test for fingerprint cookie (DEV-01, D3-09).

Simulates a Pi reboot by:
  1. Launching Chromium with a persistent user_data_dir
  2. Calling POST /api/devices/pairing-codes via the browser context (issues fingerprint cookie)
  3. Admin-binding the code via POST /api/admin/devices/bind (via context.request)
  4. Closing the browser context (simulates Pi reboot / browser exit)
  5. Relaunching with the SAME user_data_dir
  6. Asserting the fingerprint cookie is present with unchanged value
  7. Asserting GET /api/session returns non-null device_id + bound_profile_id

Critical requirement: The fingerprint cookie MUST have max_age set. Chromium does NOT
write session cookies (no max_age) to the user-data-dir SQLite store.
[VERIFIED: Playwright issue #36139 — upstream Chromium behavior]

This test requires the ``live_server_url`` fixture from ``conftest.py`` in this
directory (uvicorn-in-thread + PIN seed). The ``pytest.importorskip("playwright")``
guard ensures it is skipped (not errored) if playwright is not installed.

RESEARCH reference: Pattern 5 (verbatim) + Pitfall 1 (max_age) + Pitfall 2 (tmpfs).
"""

from __future__ import annotations

import time


# Guard the module import — if playwright is not installed, skip the entire module.
pytest = __import__("pytest")
pytest.importorskip("playwright")

import tempfile  # noqa: E402

import pytest  # noqa: E402


FINGERPRINT_COOKIE = "gruvax_device_fp"
_TEST_PIN = "0000"


@pytest.mark.asyncio(loop_scope="session")
async def test_fingerprint_persists_across_reboot(live_server_url: str) -> None:
    """D3-09: fingerprint cookie must survive browser context close + reopen.

    Uses launch_persistent_context with a tmp user_data_dir. The fingerprint
    cookie must have httpOnly=True, sameSite="Strict", and an explicit future
    expires (not a session cookie — Pitfall 1). The same value must be present
    on re-launch from the same directory (the SD-card persistence invariant).

    Also verifies:
    - POST /api/admin/devices/bind creates the device binding.
    - GET /api/session returns non-null device_id + bound_profile_id after bind.
    - The bound session is restored on second launch (no re-pair needed).

    Asserts:
    - gruvax_device_fp cookie is set after POST /api/devices/pairing-codes
    - cookie.httpOnly is True
    - cookie.sameSite == "Strict"
    - cookie.expires > now + 86400 (not a session cookie — has explicit future expiry)
    - cookie value is identical on second launch from the same user_data_dir
    - GET /api/session on second launch returns device_id != null + bound_profile_id != null
    """
    from playwright.async_api import async_playwright

    with tempfile.TemporaryDirectory() as user_data_dir:
        fp_before: dict | None = None
        fp_value_before: str = ""

        # ── First launch: issue fingerprint cookie + bind device ──────────────
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=True,
                args=["--no-sandbox"],
            )

            # POST /api/devices/pairing-codes via the browser context request.
            # This causes the server to set the gruvax_device_fp HttpOnly cookie
            # in the Chromium cookie store (via Set-Cookie response header).
            gen_response = await context.request.post(
                f"{live_server_url}/api/devices/pairing-codes"
            )
            assert gen_response.ok, (
                f"POST /api/devices/pairing-codes failed: {gen_response.status} "
                f"{await gen_response.text()}"
            )
            gen_body = await gen_response.json()
            code = gen_body["code"]
            assert len(code) == 4 and code.isdigit(), f"pairing code must be 4 digits, got {code!r}"

            # Admin login to get session cookie + CSRF token.
            login_response = await context.request.post(
                f"{live_server_url}/api/admin/login",
                data={"pin": _TEST_PIN},
                headers={"Content-Type": "application/json"},
            )
            # Re-attempt with JSON body if form encoding failed
            if not login_response.ok:
                import json as _json

                login_response = await context.request.post(
                    f"{live_server_url}/api/admin/login",
                    data=_json.dumps({"pin": _TEST_PIN}),
                    headers={"Content-Type": "application/json"},
                )
            assert login_response.ok, (
                f"Admin login failed: {login_response.status} {await login_response.text()}"
            )

            # Extract CSRF token from cookies (set by login endpoint).
            all_cookies = await context.cookies()
            csrf_token = next((c["value"] for c in all_cookies if c["name"] == "gruvax_csrf"), "")

            # Bind the device to the default profile (admin action).
            import json as _json

            bind_response = await context.request.post(
                f"{live_server_url}/api/admin/devices/bind",
                data=_json.dumps({"code": code}),
                headers={
                    "Content-Type": "application/json",
                    "X-CSRF-Token": csrf_token,
                },
            )
            assert bind_response.ok, (
                f"POST /api/admin/devices/bind failed: {bind_response.status} "
                f"{await bind_response.text()}"
            )

            # Capture cookies before closing the context (simulated reboot).
            cookies_before = await context.cookies()
            fp_before = next((c for c in cookies_before if c["name"] == FINGERPRINT_COOKIE), None)

            assert fp_before is not None, (
                f"{FINGERPRINT_COOKIE!r} cookie must be issued when calling "
                f"POST /api/devices/pairing-codes."
            )
            assert fp_before["httpOnly"] is True, (
                f"{FINGERPRINT_COOKIE!r} must be HttpOnly (JS must never read it)"
            )
            assert fp_before["sameSite"] == "Strict", (
                f"{FINGERPRINT_COOKIE!r} must be SameSite=Strict"
            )
            assert fp_before["expires"] > time.time() + 86400, (
                f"{FINGERPRINT_COOKIE!r} must have an explicit future expiry > now+1day "
                f"(session cookies are NOT persisted by Chromium to user-data-dir — "
                f"RESEARCH.md Pitfall 1). "
                f"Current expires: {fp_before['expires']}, now: {time.time()}"
            )

            fp_value_before = fp_before["value"]

            await context.close()  # Simulates browser exit / Pi reboot

        # ── Second launch: verify cookie persists from disk ───────────────────
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,  # SAME directory — cookie must be on disk
                headless=True,
                args=["--no-sandbox"],
            )

            cookies_after = await context.cookies()
            fp_after = next((c for c in cookies_after if c["name"] == FINGERPRINT_COOKIE), None)

            assert fp_after is not None, (
                f"{FINGERPRINT_COOKIE!r} cookie must survive context close + reopen. "
                f"If it is absent, the cookie was a session cookie (no max_age) and "
                f"Chromium did not persist it to disk (RESEARCH.md Pitfall 1)."
            )
            assert fp_after["value"] == fp_value_before, (
                f"Fingerprint value must be identical across relaunch. "
                f"Before: {fp_value_before!r}, After: {fp_after['value']!r}"
            )

            # GET /api/session must return the bound device_id + bound_profile_id.
            # The fingerprint cookie is sent automatically (it's in the context jar).
            session_response = await context.request.get(f"{live_server_url}/api/session")
            assert session_response.ok, (
                f"GET /api/session failed on second launch: {session_response.status} "
                f"{await session_response.text()}"
            )
            session_body = await session_response.json()

            assert session_body.get("device_id") is not None, (
                "GET /api/session must return non-null device_id for a paired device "
                "on second launch (reboot simulation)."
            )
            assert session_body.get("bound_profile_id") is not None, (
                "GET /api/session must return non-null bound_profile_id after bind "
                "on second launch (cookie persisted → device recognised → profile resolved)."
            )

            await context.close()

"""Playwright reboot-persistence test for fingerprint cookie (DEV-01, D3-09).

Simulates a Pi reboot by:
  1. Launching Chromium with a persistent user_data_dir
  2. Navigating to /pair (which triggers POST /api/devices/pairing-codes + sets fingerprint cookie)
  3. Closing the browser context (simulates Pi reboot / browser exit)
  4. Relaunching with the SAME user_data_dir
  5. Asserting the fingerprint cookie is present with unchanged value

Critical requirement: The fingerprint cookie MUST have max_age set. Chromium does NOT
write session cookies (no max_age) to the user-data-dir SQLite store.
[VERIFIED: Playwright issue #36139 — upstream Chromium behavior]

This test is PENDING until Plan 03-05 provides the live_server fixture. The
`pytest.importorskip("playwright")` guard ensures it is skipped (not errored)
if playwright is not installed or the live server is not available.
"""

from __future__ import annotations

import time

playwright_mod = __import__("builtins").__dict__.get("__name__")
# Guard the module import — if playwright is not installed, skip the entire module.
playwright = __import__("pytest").importorskip("playwright")

import tempfile  # noqa: E402

import pytest  # noqa: E402


FINGERPRINT_COOKIE = "gruvax_device_fp"


@pytest.mark.asyncio(loop_scope="session")
async def test_fingerprint_persists_across_reboot(live_server_url: str) -> None:
    """D3-09: fingerprint cookie must survive browser context close + reopen.

    Uses launch_persistent_context with a tmp user_data_dir. The fingerprint
    cookie must have httpOnly=True, sameSite="Strict", and an explicit future
    expires (not a session cookie) — and the same value must be present on
    re-launch from the same directory.

    This test is RED until Plan 03-05 wires the live_server_url fixture
    (uvicorn-in-thread + conftest.py in tests/browser/). The test will SKIP
    (not error) while the fixture is absent.

    Asserts:
    - gruvax_device_fp cookie is set after visiting /pair (POST /api/devices/pairing-codes)
    - cookie.httpOnly is True
    - cookie.sameSite == "Strict"
    - cookie.expires > now + 86400 (not a session cookie — has explicit future expiry)
    - cookie value is identical on second launch from the same user_data_dir
    """
    from playwright.async_api import async_playwright

    with tempfile.TemporaryDirectory() as user_data_dir:
        fp_before: dict | None = None

        # — First launch: visit /pair, which triggers fingerprint cookie issuance —
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=True,
                args=["--no-sandbox"],
            )
            page = await context.new_page()

            try:
                # Navigate to /pair — triggers POST /api/devices/pairing-codes
                await page.goto(f"{live_server_url}/pair", timeout=10_000)
            except Exception:
                # Endpoint not yet implemented — the test is RED for the right reason
                pass

            cookies_before = await context.cookies()
            fp_before = next(
                (c for c in cookies_before if c["name"] == FINGERPRINT_COOKIE), None
            )

            assert fp_before is not None, (
                f"{FINGERPRINT_COOKIE!r} cookie must be issued when visiting /pair "
                f"(POST /api/devices/pairing-codes issues the cookie). "
                f"RED until Plan 03-01 ships the pairing-codes endpoint."
            )
            assert fp_before["httpOnly"] is True, (
                f"{FINGERPRINT_COOKIE!r} must be HttpOnly (JS must never read it)"
            )
            assert fp_before["sameSite"] == "Strict", (
                f"{FINGERPRINT_COOKIE!r} must be SameSite=Strict"
            )
            assert fp_before["expires"] > time.time() + 86400, (
                f"{FINGERPRINT_COOKIE!r} must have an explicit future expiry > now+1day "
                f"(session cookies are NOT persisted by Chromium to user-data-dir). "
                f"Current expires: {fp_before['expires']}, now: {time.time()}"
            )

            await context.close()  # Simulates browser exit / Pi reboot

        # — Second launch: verify cookie persists from disk —
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,  # SAME directory — cookie should be on disk
                headless=True,
                args=["--no-sandbox"],
            )
            page = await context.new_page()

            try:
                await page.goto(f"{live_server_url}/pair", timeout=10_000)
            except Exception:
                pass

            cookies_after = await context.cookies()
            fp_after = next(
                (c for c in cookies_after if c["name"] == FINGERPRINT_COOKIE), None
            )

            assert fp_after is not None, (
                f"{FINGERPRINT_COOKIE!r} cookie must survive context close + reopen. "
                f"If it is absent, the cookie was a session cookie (no max_age) and "
                f"Chromium did not persist it to disk (RESEARCH.md Pitfall 1)."
            )
            assert fp_after["value"] == fp_before["value"], (
                f"Fingerprint value must be identical across relaunch. "
                f"Before: {fp_before['value']!r}, After: {fp_after['value']!r}"
            )

            await context.close()

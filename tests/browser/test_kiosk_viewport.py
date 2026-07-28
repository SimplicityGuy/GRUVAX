"""Playwright render check at the pinned kiosk viewport (gruvax-ull6).

The kiosk render target is PINNED at 800x480 (the official Raspberry Pi Touch
Display resolution — see deploy/kiosk/README.md § Target Viewport and
CLAUDE.md § Recommended Stack — Raspberry Pi Kiosk). This module is the
"CI/Playwright render check at that exact resolution" the pinning chore asked
for: it loads the public kiosk routes at exactly 800x480 and asserts the page
never grows a horizontal scrollbar, which is the layout failure mode the
viewport-dependent bugs in this batch (gruvax-k0zj's off-screen cube,
gruvax-b76z's stuck results dropdown) were found against.

Requires a built frontend (``static/`` at repo root — ``just build-spa``);
CI's ``test.yml`` builds it before running the suite. This test is scoped to
the two routes reachable without admin auth or an invite code (``/`` and
``/pair``); full route coverage (``/admin/*``, ``/redeem/:code``) is tracked
as a follow-up, not blocking this chore.

Uses the ``live_server_url`` fixture from ``conftest.py`` (uvicorn-in-thread +
PIN seed, same pattern as ``test_reboot_persistence.py``). The
``pytest.importorskip("playwright")`` guard skips (not errors) when playwright
is not installed.
"""

from __future__ import annotations


pytest = __import__("pytest")
pytest.importorskip("playwright")

import pytest  # noqa: E402


# Pinned kiosk render target — see deploy/kiosk/README.md § Target Viewport.
KIOSK_VIEWPORT = {"width": 800, "height": 480}


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("route", ["/", "/pair"])
async def test_route_fits_pinned_viewport(live_server_url: str, route: str) -> None:
    """Every kiosk route must render with zero horizontal overflow at 800x480.

    A ``document.documentElement.scrollWidth`` greater than the viewport width
    means content is being clipped or pushed off-screen sideways — the class
    of bug this pinning chore exists to make testable. (Vertical overflow is
    expected and fine — the shelf grid can legitimately scroll down; there is
    no horizontal-scroll affordance anywhere in the kiosk UI, so any
    horizontal overflow is unreachable content.)
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            page = await browser.new_page(viewport=KIOSK_VIEWPORT)
            # gruvax-dez0: NEVER wait_until="networkidle" here — the kiosk
            # route ("/") holds a persistent SSE (EventSource) connection from
            # mount, so the network never goes idle and goto times out after
            # 30s on every run. "load" is sufficient: the assertion below only
            # measures layout, and the explicit settle timeout covers the SSE
            # bootstrap / initial data fetches.
            await page.goto(f"{live_server_url}{route}", wait_until="load")

            # Let SSE bootstrap / initial data fetches settle before measuring.
            await page.wait_for_timeout(500)

            scroll_width = await page.evaluate("document.documentElement.scrollWidth")
            client_width = await page.evaluate("document.documentElement.clientWidth")

            assert scroll_width <= client_width, (
                f"{route!r} overflows the pinned 800x480 viewport horizontally: "
                f"scrollWidth={scroll_width} > clientWidth={client_width}. "
                "Content off-screen sideways is unreachable on the kiosk touch panel "
                "(no horizontal-scroll affordance exists)."
            )
        finally:
            await browser.close()

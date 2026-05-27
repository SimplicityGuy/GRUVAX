"""Trigger a discogsography → GRUVAX profile sync via the PIN-gated admin endpoint.

Usage::

    uv run gruvax-sync --profile default
    # — or piped (Plan 05 init-sync container form) —
    echo "$PIN" | uv run gruvax-sync --profile default

D-10: this CLI is intentionally SEPARATE from ``gruvax-set-pat``. It does
NOT touch the discogsography API directly — it POSTs into the running
GRUVAX FastAPI process, which owns the sync routine. The endpoint
(``POST /api/admin/profiles/{id}/sync``, Plan 04 Task 1) is PIN + CSRF
gated by the same ``require_admin`` dependency every admin write uses.

Flow:
  1. Resolve ``--profile <display_name>`` to the profile UUID by SELECT
     against ``gruvax.profiles`` (case-insensitive, soft-delete aware).
     The CLI is part of the single-deployment model (DB + API on the same
     host) so the short-lived psycopg connection is cheap and trustworthy.
  2. Read the admin PIN — TTY-aware:
       - TTY: ``getpass.getpass("Enter admin PIN (4 digits): ")``
       - Pipe: ``sys.stdin.readline().rstrip("\\n")``
     The pipe path is REQUIRED by Plan 05's init-sync container which
     runs ``echo $GRUVAX_ADMIN_PIN | gruvax-sync --profile default``.
  3. Validate PIN shape (4 numeric digits) — exit non-zero otherwise.
  4. POST /api/admin/login with the PIN; capture session cookie + CSRF.
  5. POST /api/admin/profiles/{profile_id}/sync with a generous read
     timeout (sync can take ~tens of seconds for ~3000 rows).
  6. On 200, print the response JSON to stdout (plain text, Open Q2
     RESOLVED — operators run this in compose-exec and expect plain text).
     On non-200, exit non-zero with status + body to stderr.

Security:
  - PIN never logged. The login endpoint redacts the value too (Pitfall 12).
  - CSRF double-submit honored via the X-CSRF-Token request header.
  - Session cookie is auto-carried by ``httpx.AsyncClient``'s cookie jar.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys

import httpx
import psycopg

from gruvax.settings import settings


# ── helpers ──────────────────────────────────────────────────────────────────


def _conninfo() -> str:
    """Return a vanilla psycopg conninfo string derived from settings."""
    return settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)


def _read_pin() -> str:
    """TTY → getpass; pipe → sys.stdin.readline().rstrip('\\n').

    The pipe branch is mandatory: Plan 05's init-sync compose container
    uses ``echo $GRUVAX_ADMIN_PIN | gruvax-sync --profile default``, which
    routes stdin through a pipe (NOT a TTY). ``getpass.getpass`` would
    block waiting for keyboard input that never arrives.
    """
    if sys.stdin.isatty():
        return getpass.getpass("Enter admin PIN (4 digits): ")
    return sys.stdin.readline().rstrip("\n")


def _validate_pin(pin: str) -> None:
    """Reject non-4-digit PINs before any HTTP egress."""
    if not (pin.isdigit() and len(pin) == 4):
        sys.exit("PIN must be 4 numeric digits.")


async def _resolve_profile_id(profile_name: str) -> str:
    """Look up the profile UUID by case-insensitive display_name."""
    conn = await psycopg.AsyncConnection.connect(_conninfo())
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id::text FROM gruvax.profiles "
                "WHERE LOWER(display_name) = LOWER(%s) AND deleted_at IS NULL",
                (profile_name,),
            )
            row = await cur.fetchone()
    finally:
        await conn.close()
    if row is None:
        sys.exit(f"No profile named {profile_name!r} (or it is soft-deleted).")
    return str(row[0])


async def _run_sync(profile_name: str, api_url: str) -> None:
    """End-to-end: PIN → login → sync → stdout. Every failure path sys.exits."""
    pin = _read_pin()
    _validate_pin(pin)

    profile_id = await _resolve_profile_id(profile_name)

    # Single AsyncClient — the cookie jar carries the session cookie from
    # /api/admin/login to /api/admin/profiles/{id}/sync automatically.
    # `read=120.0` because the sync runs in-process inside the API and the
    # response only returns after staging-swap + cache refresh complete
    # (~tens of seconds for ~3000 rows). The other limits stay tight.
    timeout = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)
    async with httpx.AsyncClient(base_url=api_url, timeout=timeout) as client:
        login_resp = await client.post("/api/admin/login", json={"pin": pin})
        if login_resp.status_code != 200:
            sys.exit(
                f"Admin login failed: HTTP {login_resp.status_code} — {login_resp.text}"
            )
        csrf = login_resp.cookies.get("gruvax_csrf") or login_resp.json().get("csrf_token")
        if not csrf:
            sys.exit("Admin login returned no CSRF token — cannot proceed.")

        sync_resp = await client.post(
            f"/api/admin/profiles/{profile_id}/sync",
            headers={"X-CSRF-Token": csrf},
        )
        if sync_resp.status_code != 200:
            # Plain-text status + body to stderr; exit non-zero so init-sync
            # containers fail loudly and Compose surfaces the error.
            sys.stderr.write(
                f"Sync failed: HTTP {sync_resp.status_code} — {sync_resp.text}\n"
            )
            sys.exit(1)

        # Plain text on stdout (Open Q2: operators run in compose-exec and
        # parse JSON downstream; never structlog-JSON here).
        print(sync_resp.text)  # noqa: T201 — CLI scripts intentionally print


# ── entry point ──────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gruvax-sync",
        description=(
            "Trigger a discogsography → GRUVAX profile sync via the PIN-gated "
            "admin endpoint. PIN comes from stdin (TTY: getpass; pipe: readline)."
        ),
    )
    parser.add_argument(
        "--profile",
        required=True,
        help="Profile display_name (e.g. 'default'). Matched case-insensitively.",
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("GRUVAX_BASE_URL", "http://localhost:8000"),
        help="GRUVAX API base URL (default: $GRUVAX_BASE_URL or http://localhost:8000).",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    asyncio.run(_run_sync(args.profile, args.api_url))


if __name__ == "__main__":
    main()

"""Bootstrap CLI to provision or rotate the admin PIN hash in ``gruvax.settings``.

Usage::

    uv run gruvax-set-pin

Prompts for a 4-digit numeric PIN (via ``getpass`` — not echoed), hashes it
with Argon2id, and upserts into ``gruvax.settings`` key ``auth.pin_hash``.

Security notes:
  - PIN is never stored in plaintext or written to any log.
  - Re-running this script rotates the PIN (UPSERT overwrites the old hash).
  - Existing admin sessions remain valid after rotation — they will use the
    new PIN on next verification.  To force re-login, also run a manual
    ``UPDATE gruvax.admin_sessions SET revoked_at = now()`` or use the
    Change-PIN endpoint in the admin UI (which revokes other sessions).

Requires DATABASE_URL and SESSION_SECRET in environment / .env.
"""

from __future__ import annotations

import asyncio
import getpass
import sys


async def _set_pin(pin: str) -> None:
    """Hash the PIN and upsert into gruvax.settings."""
    if not pin.isdigit() or len(pin) != 4:
        sys.exit("PIN must be exactly 4 numeric digits (e.g. 1234)")

    from gruvax.auth.pin import hash_pin
    from gruvax.db.pool import get_pool_context

    h = hash_pin(pin)

    async with get_pool_context() as pool, pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.settings (key, value, description, updated_at)"
            " VALUES ('auth.pin_hash', %s::jsonb, 'Argon2id-hashed admin PIN', now())"
            " ON CONFLICT (key) DO UPDATE"
            "  SET value = EXCLUDED.value, updated_at = now()",
            (f'"{h}"',),
        )
        await conn.commit()

    print("PIN set successfully.")


def main() -> None:
    """Entry point for ``gruvax-set-pin`` CLI script."""
    pin = getpass.getpass("Enter new PIN (4 digits): ")
    asyncio.run(_set_pin(pin))


if __name__ == "__main__":
    main()

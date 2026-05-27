"""Provision or rotate the discogsography Personal Access Token (PAT) for a profile.

Usage::

    echo "$PAT" | uv run gruvax-set-pat --profile default
    # — or interactively (paste at the hidden prompt) —
    uv run gruvax-set-pat --profile default

Flow (per CONTEXT.md D-07/D-08/D-09 and RESEARCH.md §Common operation 3):

  1. Read the PAT from STDIN ONLY. D-07 is strict: there is NO ``--pat``
     flag and the CLI ignores any ``GRUVAX_PAT`` env var. When stdin is a
     TTY we prompt via ``getpass`` (input hidden); when stdin is piped we
     read the first line.
  2. Validate prefix ``dscg_`` + total length ≥ 50.
  3. Inline test-sync against ``GET /api/user/collection?limit=1`` using
     ``DiscogsographyClient`` (D-08). Captures the response envelope's
     ``user_id`` and validates ``releases[0].catalog_number`` is present
     (if discogsography ever rolls back catalog# exposure we refuse to
     write the row).
  4. Strict rotation check (D-09): if the profile row already has a
     ``discogsography_user_id`` that differs from the captured value, exit
     non-zero with the verbatim wording defined in CONTEXT.md (D-09).
  5. Encrypt the PAT with Fernet (``GRUVAX_SECRET_KEY``) and UPDATE the
     profile row: ``app_token_encrypted``, ``app_token_revoked = FALSE``,
     ``discogsography_user_id = COALESCE(existing, captured)``.

Security rules (non-negotiable):
  - The PAT plaintext NEVER hits the DB, a log line, or stderr — the only
    persisted form is the Fernet ciphertext at rest.
  - On any failure path (rejected, mismatched, malformed envelope) the
    existing profile row is left UNTOUCHED (Pitfall 2 mitigation —
    proven by Test 5 in tests/integration/cli/test_set_pat.py).

Exit codes:
  - 0   on success.
  - !=0 with a plain-English message on every failure path. We use
    ``sys.exit("msg")`` (string) so no Python traceback leaks into the
    operator's terminal.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from typing import Any

import psycopg

from gruvax.discogsography.client import DiscogsographyClient
from gruvax.discogsography.errors import (
    NetworkError,
    PATRejected,
    RateLimitExhausted,
    ServerError,
)
from gruvax.settings import settings
from gruvax.sync.pat_crypto import encrypt_pat


# ── helpers ──────────────────────────────────────────────────────────────────


def _conninfo() -> str:
    """Return a vanilla psycopg conninfo string derived from settings."""
    return settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)


def _read_pat() -> str:
    """Read the PAT from stdin (TTY → getpass; pipe → first stdin line).

    D-07: no ``--pat`` flag, no env-var fallback. This is the only path.
    """
    if sys.stdin.isatty():
        return getpass.getpass("Paste PAT (input hidden): ").strip()
    return sys.stdin.read().strip()


def _validate_pat_shape(pat: str) -> None:
    """Reject the PAT before any HTTP egress if the prefix or length is wrong.

    Cheapest defense against typos and against pasting an obviously-wrong
    secret. The discogsography contract pins the prefix to ``dscg_``.
    """
    if not pat:
        sys.exit(
            "No PAT provided on stdin. Pipe via `echo $PAT | gruvax-set-pat ...` or run interactively."
        )
    if not pat.startswith("dscg_"):
        sys.exit("PAT must start with 'dscg_' (the discogsography v2 contract prefix). Not stored.")
    if len(pat) < 50:
        sys.exit("PAT must be at least 50 characters long. Not stored.")


async def _test_sync(pat: str) -> dict[str, Any]:
    """Hit ``GET /api/user/collection?limit=1`` and return the envelope.

    Raises ``PATRejected`` on 401/403, ``RateLimitExhausted`` on exhausted
    429s, ``ServerError`` on exhausted 5xx, ``NetworkError`` on exhausted
    connect/read timeouts. Closes the client even on error.
    """
    client = DiscogsographyClient(base_url=settings.DISCOGSOGRAPHY_BASE_URL, pat=pat)
    try:
        return await client._get_page(limit=1, offset=0)
    finally:
        await client.aclose()


def _validate_envelope(envelope: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Validate the test-sync envelope and return ``(user_id, sample_release)``.

    Refuses to proceed if:
      - ``releases`` is missing or empty,
      - ``user_id`` is missing,
      - the first release dict is missing ``catalog_number`` (D-08 —
        protects against an upstream rollback of the catalog# field).
    """
    if "user_id" not in envelope:
        sys.exit(
            "discogsography response envelope is missing user_id — refusing to write PAT. "
            "Contract drift suspected; ping the discogsography team."
        )
    releases = envelope.get("releases") or []
    if not releases:
        sys.exit(
            "discogsography sample-sync returned ZERO releases — refusing to write PAT. "
            "Either the PAT is scope-limited or this user has an empty collection."
        )
    sample = releases[0]
    if "catalog_number" not in sample:
        sys.exit(
            "discogsography sample release missing catalog_number — refusing to write PAT. "
            "The discogsography contract requires catalog_number on every release. "
            "Ping the discogsography team."
        )
    return str(envelope["user_id"]), sample


async def _commit_pat(profile_name: str, pat: str, new_user_id: str) -> None:
    """Apply the D-09 rotation check + UPDATE the profile row in one transaction.

    Uses a dedicated psycopg connection (the CLI is short-lived and not part
    of the API pool). Raises SystemExit via ``sys.exit`` for every operator-
    actionable failure path.
    """
    conn = await psycopg.AsyncConnection.connect(_conninfo())
    try:
        # Look up the profile by case-insensitive display_name (D-01 partial-unique
        # index on LOWER(display_name) WHERE deleted_at IS NULL).
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id::text, discogsography_user_id::text "
                "FROM gruvax.profiles "
                "WHERE LOWER(display_name) = LOWER(%s) AND deleted_at IS NULL",
                (profile_name,),
            )
            row = await cur.fetchone()
        if row is None:
            sys.exit(
                f"No profile named {profile_name!r} (or it is soft-deleted). "
                "Check spelling or run the migration that seeds the default profile."
            )
        profile_id, existing_user_id = row[0], row[1]

        # D-09 strict rotation check (verbatim wording from CONTEXT.md):
        if existing_user_id is not None and existing_user_id != new_user_id:
            sys.exit(
                f"PAT belongs to a different discogsography user "
                f"(was {existing_user_id}, got {new_user_id}). "
                "Soft-delete the profile first if you really intend to switch."
            )

        # Encrypt + UPDATE. COALESCE preserves an existing discogsography_user_id
        # on rotation (D-09 guarantees they match at this point).
        ciphertext = encrypt_pat(pat)
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE gruvax.profiles "
                "SET app_token_encrypted = %s, "
                "    app_token_revoked = FALSE, "
                "    discogsography_user_id = COALESCE(discogsography_user_id, %s::uuid), "
                "    last_sync_status = NULL, "
                "    last_sync_error = NULL "
                "WHERE id = %s::uuid",
                (ciphertext, new_user_id, profile_id),
            )
        await conn.commit()
    finally:
        await conn.close()


# ── orchestration ────────────────────────────────────────────────────────────


async def _set_pat(profile_name: str) -> None:
    """End-to-end: read PAT → validate → test-sync → rotation-check → UPDATE."""
    pat = _read_pat()
    _validate_pat_shape(pat)

    try:
        envelope = await _test_sync(pat)
    except PATRejected:
        sys.exit("PAT rejected by discogsography (401/403). Not stored.")
    except RateLimitExhausted:
        sys.exit(
            "discogsography rate-limited the test-sync attempt after the maximum retries. "
            "Try again in a minute. Not stored."
        )
    except ServerError as exc:
        sys.exit(f"discogsography returned a server error after retries ({exc}). Not stored.")
    except NetworkError as exc:
        sys.exit(
            f"Could not reach discogsography ({exc}). Check DISCOGSOGRAPHY_BASE_URL. Not stored."
        )

    new_user_id, _sample = _validate_envelope(envelope)
    await _commit_pat(profile_name, pat, new_user_id)

    # Operator-friendly next step. Plan 05 ships the gruvax-sync CLI; this
    # message hints at it so the owner knows what to run next. CLI scripts
    # intentionally print to stdout — same exception applied in the project
    # ruff config for scripts/*.py (cli/*.py follows the same convention).
    print(  # noqa: T201
        f"PAT stored for profile {profile_name!r} (user_id={new_user_id}). "
        f"Run `gruvax-sync --profile {profile_name}` to perform the full sync."
    )


# ── entry point ──────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser. D-07: NO --pat flag. NO env-var alternative."""
    parser = argparse.ArgumentParser(
        prog="gruvax-set-pat",
        description=(
            "Provision or rotate the discogsography PAT for a profile. "
            "Reads the PAT from STDIN only (no flag, no env var)."
        ),
    )
    parser.add_argument(
        "--profile",
        required=True,
        help="Profile display_name (e.g. 'default'). Matched case-insensitively.",
    )
    return parser


def main() -> None:
    """CLI entry point — argparse + asyncio.run(_set_pat(...))."""
    args = _build_parser().parse_args()
    asyncio.run(_set_pat(args.profile))


if __name__ == "__main__":
    main()

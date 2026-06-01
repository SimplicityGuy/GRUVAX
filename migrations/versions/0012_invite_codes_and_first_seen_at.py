"""Create profile_invite_codes table + first_seen_at column (Phase 7 / AUTH-02, API-04).

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-01

Phase 7 / v2.1:
  gruvax.profile_invite_codes — single-use, 1-hour TTL invite tokens for member self-connect.
    UUID PK (not CHAR(4)); profile_id FK ON DELETE CASCADE; consumed_at one-shot guard.
    Atomicity: UPDATE ... WHERE consumed_at IS NULL AND expires_at > NOW() RETURNING profile_id.
    FK ON DELETE CASCADE satisfies D-11: deleting a profile invalidates its outstanding invite.

  gruvax.profile_collection.first_seen_at — GRUVAX-cache arrival timestamp.
    Nullable for backfill (existing rows retain NULL — Pitfall 3).
    Set to NOW() on staging-INSERT going forward (API-04).

  gruvax.profiles.last_new_record_count, .last_sync_is_initial — stored diff state.
    Persists until next sync (D-08: stateless derivation from stored count).
    Updated atomically inside _swap_inside_tx alongside the existing profile columns.

Conventions (carried from 0001-0011):
  - from __future__ import annotations; from alembic import op
  - revision = "0012"; down_revision = "0011"; branch_labels/depends_on = None
  - ALL SQL as module-level string constants; op.execute(_CONST) in upgrade()/downgrade()
  - Never inline triple-quoted strings inside functions; never f-strings (bandit B608)
  - downgrade() fully reverses upgrade()
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | None = None
depends_on: str | None = None


# ── CREATE TABLE: gruvax.profile_invite_codes ─────────────────────────────────
# code:           UUID PK, server-generated via gen_random_uuid(). Opaque token —
#                 122-bit entropy renders brute-force infeasible (RESEARCH §Security).
# profile_id:     FK → gruvax.profiles(id) ON DELETE CASCADE. Cascade delete satisfies
#                 D-11: when a profile is deleted, its outstanding invite is invalidated.
# created_at:     immutable row creation timestamp.
# expires_at:     1-hour TTL from creation (D-01); the atomic consume WHERE clause
#                 includes AND expires_at > NOW() to reject expired codes.
# consumed_at:    one-shot guard; NULL = not yet consumed; non-NULL = already used.
#                 Atomic UPDATE ... WHERE consumed_at IS NULL RETURNING profile_id
#                 ensures "first wins" under concurrent redeem attempts (Pattern 1).
_CREATE_INVITE_CODES = (
    "CREATE TABLE IF NOT EXISTS gruvax.profile_invite_codes ("
    "  code UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  profile_id UUID NOT NULL REFERENCES gruvax.profiles(id) ON DELETE CASCADE,"
    "  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
    "  expires_at TIMESTAMPTZ NOT NULL,"
    "  consumed_at TIMESTAMPTZ"
    ")"
)


# ── INDEXES: gruvax.profile_invite_codes ─────────────────────────────────────

# Plain index on expires_at for TTL-based cleanup and expiry checks.
# Mirrors idx_pairing_codes_expires from migration 0011.
_IDX_INVITE_CODES_EXPIRES = (
    "CREATE INDEX IF NOT EXISTS idx_profile_invite_codes_expires"
    " ON gruvax.profile_invite_codes (expires_at)"
)

# Index on profile_id for the "void prior invite for this profile" query (D-09).
# The _VOID_PRIOR_INVITE query filters by profile_id to find outstanding codes.
_IDX_INVITE_CODES_PROFILE = (
    "CREATE INDEX IF NOT EXISTS idx_profile_invite_codes_profile"
    " ON gruvax.profile_invite_codes (profile_id)"
)


# ── ALTER TABLE: gruvax.profile_collection ────────────────────────────────────
# first_seen_at: GRUVAX-cache arrival timestamp. Nullable for online migration
#   (existing rows retain NULL — Pitfall 3). Set to NOW() in the staging-INSERT
#   for all rows going forward. The diff-count computation (new_record_count)
#   uses scalar pre-DELETE COUNT(*), NOT per-row first_seen_at, so NULL backfill
#   cannot mis-count on the first sync after migration (T-07-04).
_ADD_FIRST_SEEN_AT = (
    "ALTER TABLE gruvax.profile_collection"
    " ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ"
)


# ── ALTER TABLE: gruvax.profiles ─────────────────────────────────────────────
# last_new_record_count: stored diff result from the most recent swap (D-08).
#   Updated atomically in _swap_inside_tx. Persists until next sync.
#   DEFAULT 0 so existing profiles read 0 before their first sync under the new schema.
# last_sync_is_initial: True on the first-ever sync (last_sync_at WAS NULL before swap).
#   DEFAULT FALSE so existing profiles (which have already synced) read False correctly.
_ADD_PROFILE_DIFF_COLUMNS = (
    "ALTER TABLE gruvax.profiles"
    " ADD COLUMN IF NOT EXISTS last_new_record_count BIGINT DEFAULT 0,"
    " ADD COLUMN IF NOT EXISTS last_sync_is_initial BOOLEAN DEFAULT FALSE"
)


def upgrade() -> None:
    # 1. Create the invite codes table.
    op.execute(_CREATE_INVITE_CODES)

    # 2. Create indexes on the invite codes table.
    op.execute(_IDX_INVITE_CODES_EXPIRES)
    op.execute(_IDX_INVITE_CODES_PROFILE)

    # 3. Add first_seen_at to profile_collection (nullable — Pitfall 3 compliant).
    op.execute(_ADD_FIRST_SEEN_AT)

    # 4. Add diff columns to profiles (D-08 stored state).
    op.execute(_ADD_PROFILE_DIFF_COLUMNS)


def downgrade() -> None:
    # Reverse order: indexes before the table they index.
    # Tables: drop invite codes table (indexes on it are automatically dropped,
    # but we drop them explicitly for clarity and IF EXISTS safety).
    op.execute("DROP INDEX IF EXISTS gruvax.idx_profile_invite_codes_profile")
    op.execute("DROP INDEX IF EXISTS gruvax.idx_profile_invite_codes_expires")
    op.execute("DROP TABLE IF EXISTS gruvax.profile_invite_codes")

    # Reverse ALTER TABLEs — fully reverses upgrade().
    op.execute(
        "ALTER TABLE gruvax.profile_collection DROP COLUMN IF EXISTS first_seen_at"
    )
    op.execute(
        "ALTER TABLE gruvax.profiles"
        " DROP COLUMN IF EXISTS last_new_record_count,"
        " DROP COLUMN IF EXISTS last_sync_is_initial"
    )

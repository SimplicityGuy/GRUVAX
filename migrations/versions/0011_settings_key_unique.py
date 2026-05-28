"""Restore settings PK to (key) and add profile_id DEFAULT (PROF-05 compatibility).

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-28

Migration 0010 promoted ``gruvax.settings`` PK to ``(profile_id, key)`` for
per-profile data isolation. This made the existing test infrastructure (and all
other code that inserts into settings) incompatible, because:

  1. Every INSERT into ``settings`` that omits ``profile_id`` violates NOT NULL.
  2. ``ON CONFLICT (key)`` no longer matches any unique constraint.

For Phase 2 / V1 scope the admin PIN (``auth.pin_hash``) and all other settings
are GLOBAL — they apply to the installation, not to individual profiles. All
existing code reads settings with ``WHERE key = ?`` without a profile_id filter.
Requiring per-profile settings at the PK level before the application layer
actually has per-profile settings UI/API (deferred to Phase 3+) breaks every test
in the suite.

This migration:

  1. Consolidates any duplicate (key) rows across profile_ids — keeps the row
     that belongs to the DEFAULT_PROFILE_UUID, drops others.
  2. Restores the settings PRIMARY KEY to just ``(key)`` (same as pre-0010).
  3. Sets ``DEFAULT '00000000-0000-0000-0000-000000000001'::uuid`` on the
     ``profile_id`` column so existing inserts that omit it keep working.

The NOT NULL constraint on profile_id is PRESERVED — callers that explicitly
set a profile_id still get correct storage; callers that omit it get the default.

Downgrade reverses these changes to restore the 0010 state.

Round-trip note: ``alembic downgrade base`` from 0011 goes through 0010 and 0009
before reaching base. The 0010 downgrade restores the (key) PK (which is what
0011 also produces — idempotent in that direction). The 0009 downgrade drops
gruvax.profiles entirely.
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | None = None
depends_on: str | None = None


_DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"

# ── Step 1: consolidate duplicate keys ────────────────────────────────────────
# After 0010 there may be rows for the same key with different profile_ids
# (e.g. if tests or setup scripts inserted auth.pin_hash for non-default profiles).
# Keep the default-profile row; delete the rest. This must happen BEFORE we drop
# the composite PK because a non-composite unique(key) would otherwise reject the
# duplicate rows.
_DELETE_NON_DEFAULT_DUPLICATES = (
    "DELETE FROM gruvax.settings "
    "WHERE profile_id != '00000000-0000-0000-0000-000000000001'::uuid "
    "  AND key IN ("
    "    SELECT key FROM gruvax.settings "
    "    WHERE profile_id = '00000000-0000-0000-0000-000000000001'::uuid"
    "  )"
)

# ── Step 2: rebuild PK back to (key) ──────────────────────────────────────────
# Idempotent guard: only act if the PK still includes profile_id (the 0010 state).
_RESTORE_PK_SETTINGS = """
DO $$
DECLARE
    current_cols text[];
BEGIN
    SELECT array_agg(a.attname ORDER BY k.ord)
      INTO current_cols
    FROM pg_constraint con
    JOIN unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
    JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum
    WHERE con.conrelid = 'gruvax.settings'::regclass AND con.contype = 'p';

    IF current_cols IS DISTINCT FROM ARRAY['key'] THEN
        ALTER TABLE gruvax.settings DROP CONSTRAINT settings_pkey;
        ALTER TABLE gruvax.settings ADD CONSTRAINT settings_pkey PRIMARY KEY (key);
    END IF;
END $$
"""

# ── Step 3: add DEFAULT profile_id ────────────────────────────────────────────
# Callers that omit profile_id (the test fixtures, legacy code) will get the
# default profile UUID, making ON CONFLICT (key) work correctly.
_ADD_DEFAULT_PROFILE_ID = (
    "ALTER TABLE gruvax.settings "
    "ALTER COLUMN profile_id "
    "SET DEFAULT '00000000-0000-0000-0000-000000000001'::uuid"
)

# ── Downgrade: restore composite PK + remove DEFAULT ─────────────────────────
_RESTORE_COMPOSITE_PK = """
DO $$
DECLARE
    current_cols text[];
BEGIN
    SELECT array_agg(a.attname ORDER BY k.ord)
      INTO current_cols
    FROM pg_constraint con
    JOIN unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
    JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum
    WHERE con.conrelid = 'gruvax.settings'::regclass AND con.contype = 'p';

    IF current_cols IS DISTINCT FROM ARRAY['profile_id', 'key'] THEN
        ALTER TABLE gruvax.settings DROP CONSTRAINT settings_pkey;
        ALTER TABLE gruvax.settings ADD CONSTRAINT settings_pkey PRIMARY KEY (profile_id, key);
    END IF;
END $$
"""

_DROP_DEFAULT_PROFILE_ID = (
    "ALTER TABLE gruvax.settings "
    "ALTER COLUMN profile_id "
    "DROP DEFAULT"
)


def upgrade() -> None:
    # 1. Remove any per-profile duplicates before rebuilding the simpler PK.
    op.execute(_DELETE_NON_DEFAULT_DUPLICATES)
    # 2. Restore the (key)-only primary key.
    op.execute(_RESTORE_PK_SETTINGS)
    # 3. Make profile_id default to the default profile UUID so legacy inserts work.
    op.execute(_ADD_DEFAULT_PROFILE_ID)


def downgrade() -> None:
    # Remove the DEFAULT first (not strictly required, but clean).
    op.execute(_DROP_DEFAULT_PROFILE_ID)
    # Restore the composite (profile_id, key) PK.
    op.execute(_RESTORE_COMPOSITE_PK)

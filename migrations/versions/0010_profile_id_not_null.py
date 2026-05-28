"""Promote profile_id to NOT NULL on the 5 per-profile data tables (P2 / PROF-04).

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-28

Phase 2 / v2.0: tightens the nullable ``profile_id`` column that migration 0009
added (D-11) to NOT NULL on exactly the 5 per-profile DATA tables, and rebuilds
the composite PRIMARY KEY on the 4 tables whose physical/business key is now
per-profile. This makes per-profile data isolation structurally enforced at the
schema level (SC#3, the dependency root for the rest of Phase 2).

Scope split (5 data tables tightened, 2 infra tables left nullable):

  NOT NULL (5 data tables) — these hold per-profile collection/positioning state:
    cube_boundaries, settings, record_stats, segment_overrides, boundary_history

  NULLABLE kept (2 infra tables) — global/infra, not per-profile data; forcing
  NOT NULL would touch every insert site for no isolation benefit (Pitfall 5/6):
    admin_sessions, idempotency_keys

Composite PRIMARY KEY reconstruction (4 of the 5 data tables):
    cube_boundaries     (unit_id, row, col)         -> (profile_id, unit_id, row, col)
    settings            (key)                       -> (profile_id, key)
    record_stats        (release_id)                -> (profile_id, release_id)
    segment_overrides   (unit_id, row, col, label)  -> (profile_id, unit_id, row, col, label)
    boundary_history    (id BIGSERIAL) — UNCHANGED; profile_id stays a plain FK,
                        only SET NOT NULL applies.

Postgres default PK constraint name for the raw-DDL v1 tables is
``{tablename}_pkey`` (Pitfall 1 / A1) — verified against the live schema:
cube_boundaries_pkey (unit_id,row,col), settings_pkey (key),
record_stats_pkey (release_id), segment_overrides_pkey (unit_id,row,col,label).
There are zero inbound foreign keys referencing any of the 4 composite-PK tables
(verified against pg_constraint), so DROP/ADD PRIMARY KEY is safe and
lock-bounded (the ACCESS EXCLUSIVE lock is sub-second on a ~3k-row
household-scale table; T-02-01-01 accepted).

Conventions (carried from 0001-0009):
  - from __future__ import annotations; from alembic import op
  - revision = "0010"; down_revision = "0009"; branch_labels/depends_on = None
  - ALL SQL as module-level string constants; op.execute(_CONST) in upgrade()/
    downgrade(); never inline triple-quoted strings inside functions; never
    f-strings / runtime concatenation.
  - Raw op.execute SQL — NOT op.alter_column(nullable=...) — so Alembic's
    reflection path cannot mis-handle the FK + composite-PK shape (RESEARCH
    anti-pattern).
  - downgrade() fully reverses upgrade() — the CI round-trip gate
    (upgrade head -> downgrade base -> upgrade head) enforces fidelity.

Idempotence note:
  Each PK reconstruction is wrapped in a ``DO $$`` guard keyed on the table's
  current PK column array, so applying 0010 against a DB whose PK already matches
  the target is a clean no-op. SET NOT NULL is naturally idempotent. The shared
  dev DB was verified at the canonical 0009 state (cube_boundaries PK still
  (unit_id,row,col)); the guards add resilience against any future drift without
  changing the canonical fresh-0009 -> 0010 result.

Round-trip note:
  ``downgrade base`` walks all the way to 0001 and re-runs 0009's downgrade,
  whose ``v_collection`` re-creation depends on the legacy
  ``tests/fixtures/legacy/synth_collection.sql`` seed (gruvax_dev.{artists,
  releases,collection_items}) being present (Pitfall 5). The CI round-trip gate
  and ``test_migrate_0010.py``'s fixture seed it before the downgrade leg.
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | None = None
depends_on: str | None = None


# ── residual-NULL backfill (PROF-03 carry-forward) ──────────────────────────
# 0009's D-11 backfill only fixed the rows that existed *at migration time*. Any
# row written into a v1 data table AFTER 0009 (e.g. dev/seed inserts, an admin
# editing boundaries before P2 wired profile_id into the write paths) keeps a
# NULL profile_id. Before tightening to NOT NULL, sweep those stragglers onto the
# default profile (the same UUID 0009 seeded). This makes the migration runnable
# on any DB that saw writes after 0009 — without it, the verify guard below would
# make the migration permanently un-applyable on a live DB. WHERE profile_id IS
# NULL keeps it idempotent and zero-cost on an already-clean table. One static
# literal per data table — no runtime concatenation.
_DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"
_BACKFILL_CUBE_BOUNDARIES = (
    "UPDATE gruvax.cube_boundaries "
    "SET profile_id = '00000000-0000-0000-0000-000000000001'::uuid "
    "WHERE profile_id IS NULL"
)
_BACKFILL_SETTINGS = (
    "UPDATE gruvax.settings "
    "SET profile_id = '00000000-0000-0000-0000-000000000001'::uuid "
    "WHERE profile_id IS NULL"
)
_BACKFILL_RECORD_STATS = (
    "UPDATE gruvax.record_stats "
    "SET profile_id = '00000000-0000-0000-0000-000000000001'::uuid "
    "WHERE profile_id IS NULL"
)
_BACKFILL_SEGMENT_OVERRIDES = (
    "UPDATE gruvax.segment_overrides "
    "SET profile_id = '00000000-0000-0000-0000-000000000001'::uuid "
    "WHERE profile_id IS NULL"
)
_BACKFILL_BOUNDARY_HISTORY = (
    "UPDATE gruvax.boundary_history "
    "SET profile_id = '00000000-0000-0000-0000-000000000001'::uuid "
    "WHERE profile_id IS NULL"
)


# ── fail-fast NULL guards (T-02-01-02) ──────────────────────────────────────
# Defense-in-depth AFTER the backfill: if any NULL profile_id somehow survives
# (e.g. the default profile row is missing so the backfill UUID would dangle),
# RAISE EXCEPTION turns it into a loud, specific migration failure instead of a
# generic NOT-NULL violation. One static literal per data table.
_VERIFY_NO_NULLS_CUBE_BOUNDARIES = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM gruvax.cube_boundaries WHERE profile_id IS NULL) THEN
        RAISE EXCEPTION 'NULL profile_id in cube_boundaries — 0009 backfill incomplete';
    END IF;
END $$
"""
_VERIFY_NO_NULLS_SETTINGS = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM gruvax.settings WHERE profile_id IS NULL) THEN
        RAISE EXCEPTION 'NULL profile_id in settings — 0009 backfill incomplete';
    END IF;
END $$
"""
_VERIFY_NO_NULLS_RECORD_STATS = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM gruvax.record_stats WHERE profile_id IS NULL) THEN
        RAISE EXCEPTION 'NULL profile_id in record_stats — 0009 backfill incomplete';
    END IF;
END $$
"""
_VERIFY_NO_NULLS_SEGMENT_OVERRIDES = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM gruvax.segment_overrides WHERE profile_id IS NULL) THEN
        RAISE EXCEPTION 'NULL profile_id in segment_overrides — 0009 backfill incomplete';
    END IF;
END $$
"""
_VERIFY_NO_NULLS_BOUNDARY_HISTORY = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM gruvax.boundary_history WHERE profile_id IS NULL) THEN
        RAISE EXCEPTION 'NULL profile_id in boundary_history — 0009 backfill incomplete';
    END IF;
END $$
"""


# ── composite-PK reconstruction (upgrade), idempotent ───────────────────────
# Postgres has no ALTER PRIMARY KEY, so each table drops its existing _pkey and
# adds the profile_id-leading composite. Wrapped in a guard keyed on the current
# PK column array so applying against an already-rebuilt PK is a no-op while a
# fresh 0009 DB reconstructs it. Default constraint name is {tablename}_pkey
# (Pitfall 1 / A1).
_REBUILD_PK_CUBE_BOUNDARIES = """
DO $$
DECLARE
    current_cols text[];
BEGIN
    SELECT array_agg(a.attname ORDER BY k.ord)
      INTO current_cols
    FROM pg_constraint con
    JOIN unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
    JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum
    WHERE con.conrelid = 'gruvax.cube_boundaries'::regclass AND con.contype = 'p';

    IF current_cols IS DISTINCT FROM ARRAY['profile_id','unit_id','row','col'] THEN
        -- Clear whichever segment_overrides->cube_boundaries FK currently
        -- references this PK before dropping it (the old (unit_id,row,col) FK on
        -- a fresh 0009 DB, or the profile-aware FK if a prior interleaved test
        -- left it). Both DROP ... IF EXISTS are no-ops when absent; step 4 of
        -- upgrade() re-adds the profile-aware FK afterward.
        ALTER TABLE gruvax.segment_overrides
            DROP CONSTRAINT IF EXISTS segment_overrides_unit_id_row_col_fkey;
        ALTER TABLE gruvax.segment_overrides
            DROP CONSTRAINT IF EXISTS segment_overrides_profile_id_unit_id_row_col_fkey;
        ALTER TABLE gruvax.cube_boundaries DROP CONSTRAINT cube_boundaries_pkey;
        ALTER TABLE gruvax.cube_boundaries
            ADD CONSTRAINT cube_boundaries_pkey PRIMARY KEY (profile_id, unit_id, row, col);
    END IF;
END $$
"""
_REBUILD_PK_SETTINGS = """
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

    IF current_cols IS DISTINCT FROM ARRAY['profile_id','key'] THEN
        ALTER TABLE gruvax.settings DROP CONSTRAINT settings_pkey;
        ALTER TABLE gruvax.settings
            ADD CONSTRAINT settings_pkey PRIMARY KEY (profile_id, key);
    END IF;
END $$
"""
_REBUILD_PK_RECORD_STATS = """
DO $$
DECLARE
    current_cols text[];
BEGIN
    SELECT array_agg(a.attname ORDER BY k.ord)
      INTO current_cols
    FROM pg_constraint con
    JOIN unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
    JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum
    WHERE con.conrelid = 'gruvax.record_stats'::regclass AND con.contype = 'p';

    IF current_cols IS DISTINCT FROM ARRAY['profile_id','release_id'] THEN
        ALTER TABLE gruvax.record_stats DROP CONSTRAINT record_stats_pkey;
        ALTER TABLE gruvax.record_stats
            ADD CONSTRAINT record_stats_pkey PRIMARY KEY (profile_id, release_id);
    END IF;
END $$
"""
_REBUILD_PK_SEGMENT_OVERRIDES = """
DO $$
DECLARE
    current_cols text[];
BEGIN
    SELECT array_agg(a.attname ORDER BY k.ord)
      INTO current_cols
    FROM pg_constraint con
    JOIN unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
    JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum
    WHERE con.conrelid = 'gruvax.segment_overrides'::regclass AND con.contype = 'p';

    IF current_cols IS DISTINCT FROM ARRAY['profile_id','unit_id','row','col','label'] THEN
        ALTER TABLE gruvax.segment_overrides DROP CONSTRAINT segment_overrides_pkey;
        ALTER TABLE gruvax.segment_overrides
            ADD CONSTRAINT segment_overrides_pkey
            PRIMARY KEY (profile_id, unit_id, row, col, label);
    END IF;
END $$
"""


# ── segment_overrides -> cube_boundaries FK (upgrade) ───────────────────────
# segment_overrides carries an inbound composite FK
# (segment_overrides_unit_id_row_col_fkey) referencing
# cube_boundaries(unit_id, row, col) — the exact columns that 0010 rewrites into
# the new profile-leading PK. Postgres refuses to DROP cube_boundaries_pkey
# while that FK depends on it (DependentObjectsStillExist). So the FK must be
# dropped before the PK rebuild and re-added afterward, now profile-aware:
# (profile_id, unit_id, row, col) REFERENCES cube_boundaries(profile_id, unit_id,
# row, col). This keeps the cascade-delete semantics from 0005 intact and tracks
# the per-profile isolation the rest of 0010 establishes. Both statements are
# guarded with a current-state check so the migration stays idempotent.
_DROP_SEGOV_FK_OLD = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'segment_overrides_unit_id_row_col_fkey'
          AND conrelid = 'gruvax.segment_overrides'::regclass
    ) THEN
        ALTER TABLE gruvax.segment_overrides
            DROP CONSTRAINT segment_overrides_unit_id_row_col_fkey;
    END IF;
END $$
"""
_ADD_SEGOV_FK_PROFILE_AWARE = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'segment_overrides_profile_id_unit_id_row_col_fkey'
          AND conrelid = 'gruvax.segment_overrides'::regclass
    ) THEN
        ALTER TABLE gruvax.segment_overrides
            ADD CONSTRAINT segment_overrides_profile_id_unit_id_row_col_fkey
            FOREIGN KEY (profile_id, unit_id, row, col)
            REFERENCES gruvax.cube_boundaries (profile_id, unit_id, row, col)
            ON DELETE CASCADE;
    END IF;
END $$
"""

# ── segment_overrides -> cube_boundaries FK (downgrade) ─────────────────────
# Reverse of the upgrade FK swap: drop the profile-aware FK, re-add the original
# (unit_id, row, col) FK from migration 0005. Idempotent guards as above.
_DROP_SEGOV_FK_PROFILE_AWARE = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'segment_overrides_profile_id_unit_id_row_col_fkey'
          AND conrelid = 'gruvax.segment_overrides'::regclass
    ) THEN
        ALTER TABLE gruvax.segment_overrides
            DROP CONSTRAINT segment_overrides_profile_id_unit_id_row_col_fkey;
    END IF;
END $$
"""
_ADD_SEGOV_FK_OLD = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'segment_overrides_unit_id_row_col_fkey'
          AND conrelid = 'gruvax.segment_overrides'::regclass
    ) THEN
        ALTER TABLE gruvax.segment_overrides
            ADD CONSTRAINT segment_overrides_unit_id_row_col_fkey
            FOREIGN KEY (unit_id, row, col)
            REFERENCES gruvax.cube_boundaries (unit_id, row, col)
            ON DELETE CASCADE;
    END IF;
END $$
"""


# ── SET NOT NULL (upgrade) — naturally idempotent ───────────────────────────
# Raw op.execute (not op.alter_column) per the RESEARCH anti-pattern. SET NOT
# NULL on an already-NOT-NULL column is a clean no-op in Postgres.
_SET_NOT_NULL_CUBE_BOUNDARIES = (
    "ALTER TABLE gruvax.cube_boundaries ALTER COLUMN profile_id SET NOT NULL"
)
_SET_NOT_NULL_SETTINGS = "ALTER TABLE gruvax.settings ALTER COLUMN profile_id SET NOT NULL"
_SET_NOT_NULL_RECORD_STATS = "ALTER TABLE gruvax.record_stats ALTER COLUMN profile_id SET NOT NULL"
_SET_NOT_NULL_SEGMENT_OVERRIDES = (
    "ALTER TABLE gruvax.segment_overrides ALTER COLUMN profile_id SET NOT NULL"
)
_SET_NOT_NULL_BOUNDARY_HISTORY = (
    "ALTER TABLE gruvax.boundary_history ALTER COLUMN profile_id SET NOT NULL"
)


# ── DROP NOT NULL (downgrade) ───────────────────────────────────────────────
_DROP_NOT_NULL_CUBE_BOUNDARIES = (
    "ALTER TABLE gruvax.cube_boundaries ALTER COLUMN profile_id DROP NOT NULL"
)
_DROP_NOT_NULL_SETTINGS = "ALTER TABLE gruvax.settings ALTER COLUMN profile_id DROP NOT NULL"
_DROP_NOT_NULL_RECORD_STATS = (
    "ALTER TABLE gruvax.record_stats ALTER COLUMN profile_id DROP NOT NULL"
)
_DROP_NOT_NULL_SEGMENT_OVERRIDES = (
    "ALTER TABLE gruvax.segment_overrides ALTER COLUMN profile_id DROP NOT NULL"
)
_DROP_NOT_NULL_BOUNDARY_HISTORY = (
    "ALTER TABLE gruvax.boundary_history ALTER COLUMN profile_id DROP NOT NULL"
)


# ── original-PK restore (downgrade), idempotent ─────────────────────────────
# Reverse of the upgrade rebuild: restore the pre-0010 (non-profile) PKs so the
# round-trip lands the schema in the exact state 0009 left. Guarded the same way
# so a re-run is a no-op.
_RESTORE_PK_CUBE_BOUNDARIES = """
DO $$
DECLARE
    current_cols text[];
BEGIN
    SELECT array_agg(a.attname ORDER BY k.ord)
      INTO current_cols
    FROM pg_constraint con
    JOIN unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
    JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum
    WHERE con.conrelid = 'gruvax.cube_boundaries'::regclass AND con.contype = 'p';

    IF current_cols IS DISTINCT FROM ARRAY['unit_id','row','col'] THEN
        -- Clear whichever segment_overrides->cube_boundaries FK currently
        -- references this PK before dropping it. downgrade() also drops the
        -- profile-aware FK unconditionally up front, but repeating both
        -- DROP ... IF EXISTS here keeps the block self-sufficient if invoked
        -- against an interleaved half-applied state. No-ops when absent.
        ALTER TABLE gruvax.segment_overrides
            DROP CONSTRAINT IF EXISTS segment_overrides_profile_id_unit_id_row_col_fkey;
        ALTER TABLE gruvax.segment_overrides
            DROP CONSTRAINT IF EXISTS segment_overrides_unit_id_row_col_fkey;
        ALTER TABLE gruvax.cube_boundaries DROP CONSTRAINT cube_boundaries_pkey;
        ALTER TABLE gruvax.cube_boundaries
            ADD CONSTRAINT cube_boundaries_pkey PRIMARY KEY (unit_id, row, col);
    END IF;
END $$
"""
_DEDUP_SETTINGS_BEFORE_PK_RESTORE = (
    "DELETE FROM gruvax.settings "
    "WHERE profile_id != '00000000-0000-0000-0000-000000000001'::uuid "
    "  AND key IN ("
    "    SELECT key FROM gruvax.settings "
    "    WHERE profile_id = '00000000-0000-0000-0000-000000000001'::uuid"
    "  )"
)
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
        ALTER TABLE gruvax.settings
            ADD CONSTRAINT settings_pkey PRIMARY KEY (key);
    END IF;
END $$
"""
_RESTORE_PK_RECORD_STATS = """
DO $$
DECLARE
    current_cols text[];
BEGIN
    SELECT array_agg(a.attname ORDER BY k.ord)
      INTO current_cols
    FROM pg_constraint con
    JOIN unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
    JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum
    WHERE con.conrelid = 'gruvax.record_stats'::regclass AND con.contype = 'p';

    IF current_cols IS DISTINCT FROM ARRAY['release_id'] THEN
        ALTER TABLE gruvax.record_stats DROP CONSTRAINT record_stats_pkey;
        ALTER TABLE gruvax.record_stats
            ADD CONSTRAINT record_stats_pkey PRIMARY KEY (release_id);
    END IF;
END $$
"""
_RESTORE_PK_SEGMENT_OVERRIDES = """
DO $$
DECLARE
    current_cols text[];
BEGIN
    SELECT array_agg(a.attname ORDER BY k.ord)
      INTO current_cols
    FROM pg_constraint con
    JOIN unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
    JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum
    WHERE con.conrelid = 'gruvax.segment_overrides'::regclass AND con.contype = 'p';

    IF current_cols IS DISTINCT FROM ARRAY['unit_id','row','col','label'] THEN
        ALTER TABLE gruvax.segment_overrides DROP CONSTRAINT segment_overrides_pkey;
        ALTER TABLE gruvax.segment_overrides
            ADD CONSTRAINT segment_overrides_pkey
            PRIMARY KEY (unit_id, row, col, label);
    END IF;
END $$
"""


def upgrade() -> None:
    # 1. Backfill any rows written after 0009's one-time D-11 backfill (rows with
    #    a still-NULL profile_id) onto the default profile, so the tighten below
    #    can succeed on a live DB (PROF-03 carry-forward + PROF-04).
    op.execute(_BACKFILL_CUBE_BOUNDARIES)
    op.execute(_BACKFILL_SETTINGS)
    op.execute(_BACKFILL_RECORD_STATS)
    op.execute(_BACKFILL_SEGMENT_OVERRIDES)
    op.execute(_BACKFILL_BOUNDARY_HISTORY)

    # 2. Defense-in-depth: fail fast if any NULL profile_id survives the backfill
    #    (would otherwise silently corrupt per-profile isolation, T-02-01-02).
    op.execute(_VERIFY_NO_NULLS_CUBE_BOUNDARIES)
    op.execute(_VERIFY_NO_NULLS_SETTINGS)
    op.execute(_VERIFY_NO_NULLS_RECORD_STATS)
    op.execute(_VERIFY_NO_NULLS_SEGMENT_OVERRIDES)
    op.execute(_VERIFY_NO_NULLS_BOUNDARY_HISTORY)

    # 3. Drop the inbound segment_overrides -> cube_boundaries FK so the
    #    cube_boundaries PK can be rebuilt (the FK references the exact columns
    #    the PK rewrite changes; DROP CONSTRAINT would otherwise fail with
    #    DependentObjectsStillExist).
    op.execute(_DROP_SEGOV_FK_OLD)

    # 3. Reconstruct the 4 composite PRIMARY KEYs (idempotent; boundary_history
    #    keeps its surrogate id PK and is intentionally absent here).
    op.execute(_REBUILD_PK_CUBE_BOUNDARIES)
    op.execute(_REBUILD_PK_SETTINGS)
    op.execute(_REBUILD_PK_RECORD_STATS)
    op.execute(_REBUILD_PK_SEGMENT_OVERRIDES)

    # 4. Re-add the segment_overrides -> cube_boundaries FK, now profile-aware
    #    (it must reference the new (profile_id, unit_id, row, col) PK).
    op.execute(_ADD_SEGOV_FK_PROFILE_AWARE)

    # 5. SET NOT NULL on the 5 data tables. admin_sessions + idempotency_keys
    #    are deliberately untouched (Pitfall 5/6 — infra, not per-profile data).
    op.execute(_SET_NOT_NULL_CUBE_BOUNDARIES)
    op.execute(_SET_NOT_NULL_SETTINGS)
    op.execute(_SET_NOT_NULL_RECORD_STATS)
    op.execute(_SET_NOT_NULL_SEGMENT_OVERRIDES)
    op.execute(_SET_NOT_NULL_BOUNDARY_HISTORY)


def downgrade() -> None:
    # Reverse order, with PK restore BEFORE the DROP NOT NULL: Postgres refuses
    # to DROP NOT NULL on a column while it is still part of a PRIMARY KEY
    # ("column is in a primary key"), so profile_id must leave the PKs first.

    # 1. Drop the profile-aware segment_overrides -> cube_boundaries FK so the
    #    cube_boundaries PK can be restored to its original (unit_id, row, col).
    op.execute(_DROP_SEGOV_FK_PROFILE_AWARE)

    # 2. Restore the original (pre-profile) composite/simple PKs on the 4 tables.
    #    This removes profile_id from every PK so the DROP NOT NULL below is
    #    legal. 0009's backfill seeded every row to the default profile, so
    #    dropping the profile_id-leading PK leaves a valid state, no orphan rows.
    #
    #    For settings: dedup duplicate keys across profiles before restoring the
    #    simpler (key)-only PK, keeping only the default-profile rows for any key
    #    that appears under multiple profiles. This prevents UniqueViolation when
    #    per-profile default settings were seeded during normal operation.
    op.execute(_DEDUP_SETTINGS_BEFORE_PK_RESTORE)
    op.execute(_RESTORE_PK_SEGMENT_OVERRIDES)
    op.execute(_RESTORE_PK_RECORD_STATS)
    op.execute(_RESTORE_PK_SETTINGS)
    op.execute(_RESTORE_PK_CUBE_BOUNDARIES)

    # 3. Re-add the original (unit_id, row, col) FK from migration 0005, so the
    #    schema lands in the exact state 0009 left it (round-trip fidelity).
    op.execute(_ADD_SEGOV_FK_OLD)

    # 4. DROP NOT NULL on the 5 data tables LAST — now that profile_id is no
    #    longer in any PK, this restores the nullable-column shape 0009 left.
    op.execute(_DROP_NOT_NULL_BOUNDARY_HISTORY)
    op.execute(_DROP_NOT_NULL_SEGMENT_OVERRIDES)
    op.execute(_DROP_NOT_NULL_RECORD_STATS)
    op.execute(_DROP_NOT_NULL_SETTINGS)
    op.execute(_DROP_NOT_NULL_CUBE_BOUNDARIES)

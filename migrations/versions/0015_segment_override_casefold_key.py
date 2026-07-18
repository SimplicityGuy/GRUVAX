"""One casefold boundary for segment_overrides: casefolded key + display column.

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-18

Bug gruvax-rn7l.3 (supersedes gruvax-p1g): ``gruvax.segment_overrides.label`` is
the case-sensitive PK component, but every read site (the phantom-override
guard, ``SegmentCache.derive``'s override matcher, ``get_bins_for_label``)
compares via ``.casefold()``. Two writes for the same logical label that differ
only in case therefore ON CONFLICT on DIFFERENT PK rows: the second PUT INSERTs
a duplicate instead of updating the first, and — with two rows now sharing a
casefold identity — which row's fraction "wins" during re-derive depends on
which row a heap-order, unordered SELECT happens to return first (flips across
VACUUM / autovacuum re-clustering).

Fix (ADR-0001 item 4 / docs/design/adr-0001-normalization-authority.md):
Python is the normalization authority. ``label`` becomes a casefolded STORAGE
KEY, normalized uniformly at every write site (segments.py's single-override
endpoint, cubes.py's put_cube_boundary + bulk_write_cubes override-carry
paths). A new ``label_display`` column carries the original-case string for
the admin UI, independent of the PK.

This migration:
  1. Adds ``label_display`` (nullable) and backfills it from the current
     ``label`` value (the only original-case string available at migration
     time — later writes populate it from the request's original-case input).
  2. Deduplicates existing case-variant rows that collide once ``label`` is
     casefolded: for every (profile_id, unit_id, row, col, lower(label))
     group, keeps the most-recently updated row (ties broken by ``label``
     ascending for a deterministic result) and deletes the rest.
  3. Casefolds the ``label`` column in place for all surviving rows so the PK
     itself carries only casefolded values from this point forward.

``label_display`` is intentionally left NULLABLE at the DB layer (not NOT
NULL): every application write site (segments.py's single-override endpoint,
import_.py's boundary-import upsert) always supplies it, but a handful of
existing direct-SQL tests (test_migrate_0005.py's fraction-CHECK probes)
insert bare ``segment_overrides`` rows to exercise a DIFFERENT constraint in
isolation. Making the column NOT NULL would turn those into unrelated
NotNullViolation failures instead of exercising the fraction CHECK they
target. The display column existing-but-nullable is a strictly safer schema
change than adding a new mandatory column that couples this migration to
every prior test's INSERT shape.

Irreversibility note: step 2 deletes rows and step 3 rewrites ``label`` values
in place — the original per-row casing of collided duplicates is not
recoverable. ``downgrade()`` restores the SCHEMA (drops ``label_display``)
but, consistent with every other lossy backfill in this migration chain
(0013/0014 FTS rebuilds), does not attempt to reconstruct pre-migration data.
The CI round-trip gate (``alembic upgrade head && downgrade base && upgrade
head``) exercises schema state, not data fidelity.

Conventions (carried from 0001-0014):
  - All DDL/DML via op.execute() with explicit statements.
  - downgrade() drops what upgrade() added, IF EXISTS guards throughout.
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | None = None
depends_on: str | None = None


_ADD_LABEL_DISPLAY = "ALTER TABLE gruvax.segment_overrides ADD COLUMN IF NOT EXISTS label_display TEXT"

_BACKFILL_LABEL_DISPLAY = (
    "UPDATE gruvax.segment_overrides SET label_display = label WHERE label_display IS NULL"
)

# Keep the most-recently-updated row per casefold-identity group; delete the rest.
# Tie-break on `label` ascending so the outcome is deterministic even when two
# rows share the exact same updated_at timestamp.
_DEDUPE_CASE_VARIANTS = """
WITH ranked AS (
    SELECT
        profile_id, unit_id, "row", col, label,
        ROW_NUMBER() OVER (
            PARTITION BY profile_id, unit_id, "row", col, lower(label)
            ORDER BY updated_at DESC, label ASC
        ) AS rn
    FROM gruvax.segment_overrides
)
DELETE FROM gruvax.segment_overrides so
USING ranked
WHERE so.profile_id = ranked.profile_id
  AND so.unit_id = ranked.unit_id
  AND so."row" = ranked."row"
  AND so.col = ranked.col
  AND so.label = ranked.label
  AND ranked.rn > 1
"""

# Safe post-dedupe: no two surviving rows in the same (profile_id, unit_id, row,
# col) group can still collide on lower(label) once _DEDUPE_CASE_VARIANTS ran.
_CASEFOLD_LABEL_KEY = (
    "UPDATE gruvax.segment_overrides SET label = lower(label) WHERE label <> lower(label)"
)

_DROP_LABEL_DISPLAY = "ALTER TABLE gruvax.segment_overrides DROP COLUMN IF EXISTS label_display"


def upgrade() -> None:
    op.execute(_ADD_LABEL_DISPLAY)
    op.execute(_BACKFILL_LABEL_DISPLAY)
    op.execute(_DEDUPE_CASE_VARIANTS)
    op.execute(_CASEFOLD_LABEL_KEY)


def downgrade() -> None:
    # Schema-only reversal (see Irreversibility note above): the dedupe/casefold
    # data transform is not recoverable, matching the lossy-backfill precedent
    # set by 0013/0014.
    op.execute(_DROP_LABEL_DISPLAY)

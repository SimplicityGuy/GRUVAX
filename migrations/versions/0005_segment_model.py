"""Drop last_* columns from cube_boundaries; add segment_overrides table.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-22

Phase 5: Segment-Aware Position Precision (SEG-01)

Transforms ``gruvax.cube_boundaries`` from the one-span-per-cube model to the
cut-point model:

- Drops ``last_label`` and ``last_catalog`` columns (now derived by SegmentCache
  from the next cube's cut point + CollectionSnapshot row counts).
- Replaces the ``empty_or_complete`` CHECK constraint with ``cut_point_complete``
  (a cube is valid with only first_* columns populated, since last_* are derived).
- Extends ``boundary_history.source`` CHECK to include ``'cut_insert'`` for the
  new cut-point insert operation (SEG-08). The existing prev_last_* / new_last_*
  columns on boundary_history are KEPT as nullable historical artifact (A1 — no
  audit data is destroyed by this migration).
- Creates ``gruvax.segment_overrides`` table: optional admin physical-width
  overrides per label-segment per bin (SEG-04). The fraction CHECK bounds overrides
  to (0.0, 1.0] at the storage layer (T-05-01 security control, V5 input validation).

Conventions (carried from 0001-0004):
- All DDL via op.execute() with explicit constraint/index names.
- downgrade() drops/restores in reverse with IF EXISTS guards.
- alembic_version in public; search_path via connect listener (env.py unchanged).
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ── 1. Drop derived columns (now computed by SegmentCache) ────────────────
    # last_label and last_catalog are derived from the next cube's cut point;
    # storing them is redundant and can diverge from the derived truth.
    op.execute("""
        ALTER TABLE gruvax.cube_boundaries
            DROP COLUMN IF EXISTS last_label,
            DROP COLUMN IF EXISTS last_catalog
    """)

    # ── 2. Replace CHECK constraint for the cut-point model ───────────────────
    # empty_or_complete required all four bound columns (first_* + last_*).
    # cut_point_complete only requires first_* (last_* are now derived).
    op.execute("ALTER TABLE gruvax.cube_boundaries DROP CONSTRAINT IF EXISTS empty_or_complete")
    op.execute("""
        ALTER TABLE gruvax.cube_boundaries
            ADD CONSTRAINT cut_point_complete CHECK (
                is_empty
                OR (first_label IS NOT NULL AND first_catalog IS NOT NULL)
            )
    """)

    # ── 3. Extend boundary_history.source CHECK with 'cut_insert' ─────────────
    # Keep prev_last_* / new_last_* columns as nullable historical artifact (A1).
    # Only the source CHECK is updated to allow the new 'cut_insert' operation.
    op.execute(
        "ALTER TABLE gruvax.boundary_history"
        " DROP CONSTRAINT IF EXISTS boundary_history_source_check"
    )
    op.execute("""
        ALTER TABLE gruvax.boundary_history
            ADD CONSTRAINT boundary_history_source_check
            CHECK (source IN ('manual', 'bulk', 'revert', 'cut_insert'))
    """)

    # ── 4. Create gruvax.segment_overrides ────────────────────────────────────
    # Optional admin physical-width overrides per label-segment per bin (SEG-04).
    # fraction CHECK bounds the value to (0.0, 1.0] at the storage layer —
    # this is the T-05-01 / V5 security control (fraction=0.0 would erase a
    # segment; fraction>1.0 is geometrically impossible for a sub-cube band).
    # FK (unit_id, row, col) -> cube_boundaries ON DELETE CASCADE ensures
    # overrides are cleaned up when a bin is removed (T-05-02).
    op.execute("""
        CREATE TABLE gruvax.segment_overrides (
            unit_id     SMALLINT    NOT NULL
                            REFERENCES gruvax.units(id) ON DELETE RESTRICT,
            row         SMALLINT    NOT NULL,
            col         SMALLINT    NOT NULL,
            label       TEXT        NOT NULL,
            fraction    REAL        NOT NULL
                            CHECK (fraction > 0.0 AND fraction <= 1.0),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (unit_id, row, col, label),
            FOREIGN KEY (unit_id, row, col)
                REFERENCES gruvax.cube_boundaries (unit_id, row, col) ON DELETE CASCADE
        )
    """)


def downgrade() -> None:
    # Drop in reverse order; IF EXISTS guards make this idempotent.
    # NOTE: last_* columns must be added BEFORE the empty_or_complete CHECK
    # that references them is added (ordering is critical for round-trip).

    # 4. Drop segment_overrides
    op.execute("DROP TABLE IF EXISTS gruvax.segment_overrides")

    # 3. Restore boundary_history.source CHECK to the original 3-value set
    op.execute(
        "ALTER TABLE gruvax.boundary_history"
        " DROP CONSTRAINT IF EXISTS boundary_history_source_check"
    )
    op.execute("""
        ALTER TABLE gruvax.boundary_history
            ADD CONSTRAINT boundary_history_source_check
            CHECK (source IN ('manual', 'bulk', 'revert'))
    """)

    # 2a. Re-add the last_* columns FIRST (nullable — existing rows have no data for them)
    #     Must precede the empty_or_complete CHECK which references them.
    op.execute("""
        ALTER TABLE gruvax.cube_boundaries
            ADD COLUMN IF NOT EXISTS last_label   TEXT,
            ADD COLUMN IF NOT EXISTS last_catalog TEXT
    """)

    # 2b. Restore the original empty_or_complete CHECK (requires all four bound columns)
    #     Use NOT VALID so the constraint is added without scanning existing rows —
    #     downgraded rows have last_label=NULL because the data was not preserved
    #     when the 0005 upgrade dropped those columns. NOT VALID means the constraint
    #     applies to future INSERTs/UPDATEs but does not fail on pre-existing rows.
    op.execute("ALTER TABLE gruvax.cube_boundaries DROP CONSTRAINT IF EXISTS cut_point_complete")
    op.execute("""
        ALTER TABLE gruvax.cube_boundaries
            ADD CONSTRAINT empty_or_complete CHECK (
                is_empty
                OR (
                    first_label   IS NOT NULL
                    AND first_catalog IS NOT NULL
                    AND last_label    IS NOT NULL
                    AND last_catalog  IS NOT NULL
                )
            ) NOT VALID
    """)

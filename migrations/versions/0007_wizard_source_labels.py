"""Extend boundary_history.source CHECK for wizard/import source labels.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-24

Phase 7: Adds 'wizard', 'reshuffle', 'csv', 'yaml' to the source CHECK
constraint so wizard commits and imports appear with legible labels in
the History view (D-04).

Conventions (carried from 0001-0006):
- All DDL via op.execute() with explicit constraint/index names.
- downgrade() reverses back to the Phase 5 set (no data loss for a
  dev/CI round-trip; production rows with new sources are not expected
  during a downgrade — T-07-02 accepted risk).
- alembic_version in public; search_path via connect listener (env.py).
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Drop the Phase 5 constraint and replace with the Phase 7 expanded set.
    # Two-step DROP+ADD is required because ALTER CONSTRAINT is not supported
    # for CHECK constraints in PostgreSQL.
    op.execute(
        "ALTER TABLE gruvax.boundary_history"
        " DROP CONSTRAINT IF EXISTS boundary_history_source_check"
    )
    op.execute("""
        ALTER TABLE gruvax.boundary_history
            ADD CONSTRAINT boundary_history_source_check
            CHECK (source IN (
                'manual', 'bulk', 'revert', 'cut_insert',
                'wizard', 'reshuffle', 'csv', 'yaml'
            ))
    """)


def downgrade() -> None:
    # Restore to the Phase 5 set: ('manual', 'bulk', 'revert', 'cut_insert').
    # T-07-02 accepted risk: rows with source in ('wizard','reshuffle','csv','yaml')
    # added after the upgrade will violate this constraint after downgrade.
    # This downgrade is only expected in dev/CI round-trip scenarios.
    op.execute(
        "ALTER TABLE gruvax.boundary_history"
        " DROP CONSTRAINT IF EXISTS boundary_history_source_check"
    )
    op.execute("""
        ALTER TABLE gruvax.boundary_history
            ADD CONSTRAINT boundary_history_source_check
            CHECK (source IN ('manual', 'bulk', 'revert', 'cut_insert'))
    """)

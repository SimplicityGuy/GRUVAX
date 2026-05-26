"""Create gruvax schema, units table, and cube_boundaries table.

Revision ID: 0001
Revises:
Create Date: 2026-05-20

DDL is per ARCHITECTURE.md §"Database Schema".  Naming conventions use explicit
constraint names so that autogenerate and CI round-trips produce stable output.
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ── Create schema ─────────────────────────────────────────────────────────
    op.execute("CREATE SCHEMA IF NOT EXISTS gruvax")

    # ── gruvax.units ──────────────────────────────────────────────────────────
    # Configurable shelving units.  Two today (left/right Kallax 4x4),
    # more later without schema change.
    op.execute("""
        CREATE TABLE gruvax.units (
            id            SMALLSERIAL PRIMARY KEY,
            display_name  TEXT        NOT NULL,
            rows          SMALLINT    NOT NULL,
            cols          SMALLINT    NOT NULL,
            ordering      SMALLINT    NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # ── gruvax.cube_boundaries ────────────────────────────────────────────────
    # Per-cube first/last (label, catalog#) bounds.  ~32 rows at v1 N=2.
    #
    # Boundary semantics: a record (label, catalog#) belongs in this cube iff
    #   (first_label, first_catalog) <= (label, catalog#) <= (last_label, last_catalog)
    # under the project's chosen sort order (POS-01 normalised comparator).
    #
    # Constraint empty_or_complete: a cube is either explicitly empty OR all
    # four bound columns must be non-NULL.  This prevents half-filled boundaries.
    op.execute("""
        CREATE TABLE gruvax.cube_boundaries (
            unit_id        SMALLINT    NOT NULL
                               REFERENCES gruvax.units(id) ON DELETE RESTRICT,
            row            SMALLINT    NOT NULL,
            col            SMALLINT    NOT NULL,
            first_label    TEXT,
            first_catalog  TEXT,
            last_label     TEXT,
            last_catalog   TEXT,
            is_empty       BOOLEAN     NOT NULL DEFAULT FALSE,
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (unit_id, row, col),
            CONSTRAINT empty_or_complete CHECK (
                is_empty
                OR (
                    first_label   IS NOT NULL
                    AND first_catalog IS NOT NULL
                    AND last_label    IS NOT NULL
                    AND last_catalog  IS NOT NULL
                )
            )
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gruvax.cube_boundaries")
    op.execute("DROP TABLE IF EXISTS gruvax.units")
    # alembic_version lives in public (not in gruvax) so DROP SCHEMA without
    # CASCADE is safe once the application tables are dropped above.
    op.execute("DROP SCHEMA IF EXISTS gruvax")

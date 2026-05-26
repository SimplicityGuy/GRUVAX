"""Create gruvax.record_stats — durable search/selection counters (D-04/D-05/D-06).

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-24

Phase 8: Adds the record_stats table for OBS-07 (most-searched diagnostics).
Counters are release_id-keyed aggregates; no query text is ever stored (OBS-07).

Conventions (carried from 0001-0007):
- All DDL via op.execute() with explicit constraint/index names.
- downgrade() fully reverses upgrade().
- alembic_version in public; search_path via connect listener (env.py).
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | None = None
depends_on: str | None = None


_CREATE_TABLE = """
CREATE TABLE gruvax.record_stats (
    release_id          BIGINT        PRIMARY KEY,
    search_count        BIGINT        NOT NULL DEFAULT 0,
    search_count_7d     BIGINT        NOT NULL DEFAULT 0,
    selection_count     BIGINT        NOT NULL DEFAULT 0,
    selection_count_7d  BIGINT        NOT NULL DEFAULT 0,
    last_searched_at    TIMESTAMPTZ,
    last_selected_at    TIMESTAMPTZ,
    updated_at          TIMESTAMPTZ   NOT NULL DEFAULT now()
)
"""

_CREATE_IDX = "CREATE INDEX ix_record_stats_search_count ON gruvax.record_stats (search_count DESC)"

_DROP_IDX = "DROP INDEX IF EXISTS gruvax.ix_record_stats_search_count"
_DROP_TABLE = "DROP TABLE IF EXISTS gruvax.record_stats"


def upgrade() -> None:
    op.execute(_CREATE_TABLE)
    op.execute(_CREATE_IDX)


def downgrade() -> None:
    op.execute(_DROP_IDX)
    op.execute(_DROP_TABLE)

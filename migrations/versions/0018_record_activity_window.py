"""Track actual record activity timestamps for exact trailing seven-day counts.

Revision ID: 0018
Revises: 0017

Historical lifetime counters are preserved. Old aggregate timestamps cannot
reconstruct individual events: exact window tracking starts at this upgrade.
Downgrade refuses to discard any active-window history, including the default
profile, before performing DDL. Only expired derived history can be discarded.
"""

from alembic import op

from gruvax.db.migration_safety import ACTIVITY_DOWNGRADE_GUARD


revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE gruvax.record_activity (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    profile_id UUID NOT NULL REFERENCES gruvax.profiles(id) ON DELETE CASCADE,
    release_id BIGINT NOT NULL,
    event_kind TEXT NOT NULL CHECK (event_kind IN ('search', 'selection')),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")
    op.execute(
        "CREATE INDEX record_activity_window_idx ON gruvax.record_activity (profile_id, release_id, occurred_at)"
    )
    op.execute(
        "CREATE INDEX record_activity_expiry_idx ON gruvax.record_activity (profile_id, occurred_at)"
    )
    op.execute(
        "COMMENT ON TABLE gruvax.record_activity IS 'Exact seven-day activity tracking starts with migration 0018; historical lifetime totals have no reconstructible event timestamps.'"
    )
    # These compatibility caches must not carry the old consecutive-gap counts
    # into the new exact window. Lifetime totals and last-event times stay intact.
    op.execute("UPDATE gruvax.record_stats SET search_count_7d = 0, selection_count_7d = 0")


def downgrade() -> None:
    op.execute(ACTIVITY_DOWNGRADE_GUARD)
    op.execute("DROP TABLE gruvax.record_activity")

"""Tag snapshot contract failures without losing status on downgrade.

Revision ID: 0019
Revises: 0018
Downgrade refuses before DDL when any profile holds the new error value.
"""

from alembic import op

from gruvax.db.migration_safety import SNAPSHOT_ERROR_DOWNGRADE_GUARD


revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

_OLD = "last_sync_error IN ('pat_rejected','network','rate_limited','server_error','cancelled','shrink_guard') OR last_sync_error IS NULL"
_NEW = "last_sync_error IN ('pat_rejected','network','rate_limited','server_error','cancelled','shrink_guard','snapshot_mismatch') OR last_sync_error IS NULL"


def _set_check(expression: str) -> None:
    op.execute("ALTER TABLE gruvax.profiles DROP CONSTRAINT profiles_last_sync_error_check")
    op.execute(
        f"ALTER TABLE gruvax.profiles ADD CONSTRAINT profiles_last_sync_error_check CHECK ({expression})"
    )


def upgrade() -> None:
    _set_check(_NEW)


def downgrade() -> None:
    op.execute(SNAPSHOT_ERROR_DOWNGRADE_GUARD)
    _set_check(_OLD)

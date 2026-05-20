"""Enable pg_trgm extension for trigram-similarity did-you-mean search (SRCH-07/08).

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-20

The pg_trgm extension provides the ``similarity()`` function and the
``%`` operator used by ``did_you_mean_query`` in ``queries.py``.

Upgrade:
    Attempts ``CREATE EXTENSION IF NOT EXISTS pg_trgm``.  If the role
    running migrations lacks superuser / CREATE privileges, the attempt is
    silently swallowed so the rest of the migration chain succeeds.  The
    application degrades gracefully when pg_trgm is absent: every call to
    ``did_you_mean_query`` catches ``psycopg.errors.UndefinedFunction`` and
    returns ``None`` (Pitfall E — SRCH-07/08).

Downgrade:
    No-op.  Shared extensions are never dropped via application migrations;
    they are cleaned up manually by the DBA if needed.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # pg_trgm: attempt silently; app degrades if unavailable (Pitfall E).
    # Insufficient privileges or missing extension will be caught and ignored.
    try:
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    except Exception:
        pass  # Insufficient privileges — SRCH-07/08 degrade gracefully


def downgrade() -> None:
    pass  # Never drop a shared extension; GIN indexes dropped with schema

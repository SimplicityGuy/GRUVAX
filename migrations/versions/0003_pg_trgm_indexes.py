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

import contextlib

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # pg_trgm: attempt silently; app degrades if unavailable (Pitfall E).
    # Insufficient privileges or a missing extension are caught and ignored so
    # the migration chain still succeeds; SRCH-07/08 degrade gracefully.
    # SCHEMA public is required so the extension lives outside `gruvax`; otherwise
    # alembic's search_path lands it inside `gruvax`, and DROP SCHEMA gruvax in the
    # 0001 downgrade fails the CI round-trip with "extension pg_trgm depends on
    # schema gruvax" (pg_trgm is a shared/public extension by intent).
    with contextlib.suppress(Exception):
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA public")


def downgrade() -> None:
    pass  # Never drop a shared extension; GIN indexes dropped with schema

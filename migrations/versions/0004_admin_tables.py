"""Create admin tables: boundary_history, admin_sessions, settings, idempotency_keys.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-21

Adds four tables to the ``gruvax`` schema required for Phase 3 admin loop:

- ``boundary_history``   — append-only audit log of cube-boundary changes, grouped
                           by ``change_set_id``.  Supports undo (source='revert').
- ``admin_sessions``     — server-side session rows; enables revocation on PIN change
                           and hard session cap independent of sliding TTL.
- ``settings``           — key/value JSONB store for runtime configuration
                           (PIN hash, capacity, session TTL).  Seeded with Phase 3
                           defaults.
- ``idempotency_keys``   — 24h dedup store for ``POST /api/admin/cubes/bulk`` so
                           a client retry cannot double-commit a change-set.

Conventions (carried from 0001-0003):
- All DDL via ``op.execute()`` with explicit constraint/index names.
- ``downgrade()`` drops tables in reverse creation order with IF EXISTS guards.
- ``migrations/env.py`` is NOT modified; ``version_table_schema="public"`` and
  the ``search_path`` connect-event listener already handle the new tables.
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ── gruvax.boundary_history ───────────────────────────────────────────────
    # Append-only audit log; one row per cube per change-set.
    # ``source`` CHECK constraint keeps the allowed values explicit.
    op.execute("""
        CREATE TABLE gruvax.boundary_history (
            id                  BIGSERIAL       PRIMARY KEY,
            change_set_id       UUID            NOT NULL,
            unit_id             SMALLINT        NOT NULL,
            row                 SMALLINT        NOT NULL,
            col                 SMALLINT        NOT NULL,
            prev_first_label    TEXT,
            prev_first_catalog  TEXT,
            prev_last_label     TEXT,
            prev_last_catalog   TEXT,
            prev_is_empty       BOOLEAN         NOT NULL,
            new_first_label     TEXT,
            new_first_catalog   TEXT,
            new_last_label      TEXT,
            new_last_catalog    TEXT,
            new_is_empty        BOOLEAN         NOT NULL,
            changed_by          TEXT            NOT NULL DEFAULT 'admin',
            changed_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
            source              TEXT            NOT NULL
                CHECK (source IN ('manual', 'bulk', 'revert'))
        )
    """)
    # DESC index for history-view queries ordered newest-first.
    op.execute("CREATE INDEX bh_changed_at_idx ON gruvax.boundary_history (changed_at DESC)")
    # Index for revert queries that look up all rows in a change-set.
    op.execute("CREATE INDEX bh_change_set_idx ON gruvax.boundary_history (change_set_id)")

    # ── gruvax.admin_sessions ─────────────────────────────────────────────────
    # Server-side session rows; signed session token stored in HttpOnly cookie.
    # ``hard_expires_at`` is independent of sliding idle TTL (D-03d, Pitfall 23).
    # ``revoked_at`` enables immediate revocation on logout or PIN change.
    op.execute("""
        CREATE TABLE gruvax.admin_sessions (
            id              UUID            PRIMARY KEY,
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
            last_seen_at    TIMESTAMPTZ     NOT NULL DEFAULT now(),
            expires_at      TIMESTAMPTZ     NOT NULL,
            hard_expires_at TIMESTAMPTZ     NOT NULL,
            client_label    TEXT,
            user_agent      TEXT,
            revoked_at      TIMESTAMPTZ
        )
    """)
    # Partial index: only non-revoked sessions need fast expiry lookups.
    op.execute("""
        CREATE INDEX admin_sessions_expires_idx
            ON gruvax.admin_sessions (expires_at)
            WHERE revoked_at IS NULL
    """)

    # ── gruvax.settings ───────────────────────────────────────────────────────
    # Key/value JSONB store for runtime configuration.  ``value`` is JSONB so
    # numbers are stored as JSON numbers (no quoting needed for numeric reads).
    op.execute("""
        CREATE TABLE gruvax.settings (
            key         TEXT        PRIMARY KEY,
            value       JSONB       NOT NULL,
            description TEXT,
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    # Seed Phase 3 defaults.
    # cube.nominal_capacity: ~95 LPs per Kallax cube (D-13, Claude's discretion).
    # session.idle_ttl_seconds: 10-minute idle window (D-04).
    # session.hard_cap_seconds: 30-minute hard cap (D-03d, Claude's discretion).
    op.execute("""
        INSERT INTO gruvax.settings (key, value, description) VALUES
        (
            'cube.nominal_capacity',
            '95',
            'Nominal LP capacity per Kallax cube for fill-level gauge (D-13)'
        ),
        (
            'session.idle_ttl_seconds',
            '600',
            'Admin session idle timeout in seconds — 10 minutes (D-04)'
        ),
        (
            'session.hard_cap_seconds',
            '1800',
            'Hard admin session cap in seconds — 30 minutes (D-03d, Pitfall 23)'
        )
    """)

    # ── gruvax.idempotency_keys ───────────────────────────────────────────────
    # 24-hour dedup store for POST /api/admin/cubes/bulk (D-10 / Pitfall 7).
    # Application cleans up old rows on each bulk request (cheap: indexed on
    # created_at).
    op.execute("""
        CREATE TABLE gruvax.idempotency_keys (
            key             TEXT        PRIMARY KEY,
            response_json   JSONB       NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idempotency_keys_created_idx ON gruvax.idempotency_keys (created_at)")


def downgrade() -> None:
    # Drop in reverse creation order; IF EXISTS guards make this idempotent.
    op.execute("DROP TABLE IF EXISTS gruvax.idempotency_keys")
    op.execute("DROP TABLE IF EXISTS gruvax.settings")
    op.execute("DROP TABLE IF EXISTS gruvax.admin_sessions")
    op.execute("DROP TABLE IF EXISTS gruvax.boundary_history")

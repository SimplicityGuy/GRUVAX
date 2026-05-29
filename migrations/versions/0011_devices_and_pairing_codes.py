"""Create devices + pairing_codes tables (P3 / DEV-01).

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-29

Phase 3 / v2.0: introduces the device persistence model (DEV-01) for the
GRUVAX Devices + Pairing feature. Two new tables:

  gruvax.devices — persists the device-to-profile binding for each RPi kiosk.
    Identified by an opaque HttpOnly fingerprint cookie (secrets.token_urlsafe(32)).
    profile_id is nullable (ON DELETE SET NULL) so a profile soft-delete orphans
    the device (sets profile_id NULL) rather than cascade-deleting the device row —
    the kiosk then falls back to the profile picker (D3-05).

  gruvax.pairing_codes — short-lived CHAR(4) codes with a 5-minute TTL and a
    one-shot consumed_at guard. The atomicity invariant ("first wins") is enforced
    by a single UPDATE ... WHERE consumed_at IS NULL RETURNING ... at READ COMMITTED
    isolation — the first transaction to write consumed_at holds the row lock; any
    concurrent attempt re-evaluates the WHERE clause and sees consumed_at IS NOT NULL.

Indexes:
  idx_devices_fingerprint_active — UNIQUE partial (WHERE revoked_at IS NULL):
    enforces one active row per fingerprint; used by per-request device check (D3-07).
  idx_devices_fingerprint — plain non-partial:
    for revoke-guard lookups that must also find revoked rows (RESEARCH.md Pitfall 5 /
    Open Question 2 — partial index cannot satisfy queries without the partial predicate).
  idx_devices_profile_active — UNIQUE partial (WHERE revoked_at IS NULL AND profile_id IS NOT NULL):
    enforces one active device per profile; allows NULL profile_id (orphaned devices).
  idx_pairing_codes_expires — plain on expires_at:
    for TTL-based cleanup queries.

Conventions (carried from 0001-0010):
  - from __future__ import annotations; from alembic import op
  - revision = "0011"; down_revision = "0010"; branch_labels/depends_on = None
  - ALL SQL as module-level string constants; op.execute(_CONST) in upgrade()/
    downgrade(); never inline triple-quoted strings inside functions; never
    f-strings / runtime concatenation (bandit B608).
  - downgrade() fully reverses upgrade() — the CI round-trip gate
    (upgrade head -> downgrade -1 -> upgrade head) enforces fidelity.
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | None = None
depends_on: str | None = None


# ── CREATE TABLE: gruvax.devices ─────────────────────────────────────────────
# id:           UUID PK, server-generated via gen_random_uuid().
# fingerprint:  opaque HttpOnly cookie value (secrets.token_urlsafe(32) — 256-bit
#               CSPRNG entropy). Stored plain (not hashed) on LAN; never logged.
# profile_id:   nullable FK → gruvax.profiles(id) ON DELETE SET NULL; NULL means
#               the device is orphaned (profile soft-deleted) and falls back to
#               the profile picker (D3-05).
# display_name: admin-assigned human label; defaults to 'Unnamed device'.
# revoked_at:   non-NULL → device is revoked; per-request guard (D3-07) returns 403.
# last_seen_at: updated (throttled) on each authenticated device request.
# created_at:   immutable row creation timestamp.
_CREATE_DEVICES = (
    "CREATE TABLE IF NOT EXISTS gruvax.devices ("
    "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  fingerprint TEXT NOT NULL,"
    "  profile_id UUID REFERENCES gruvax.profiles(id) ON DELETE SET NULL,"
    "  display_name TEXT NOT NULL DEFAULT 'Unnamed device',"
    "  revoked_at TIMESTAMPTZ,"
    "  last_seen_at TIMESTAMPTZ,"
    "  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
    ")"
)


# ── CREATE TABLE: gruvax.pairing_codes ───────────────────────────────────────
# code:         CHAR(4) PK — zero-padded 4-digit string ('0000'..'9999').
#               PK uniqueness enforces one live code per value at any time.
# fingerprint:  the kiosk's fingerprint; set when the /pair page generates a code.
# created_at:   immutable; used for audit.
# expires_at:   5-minute TTL; codes past this timestamp are rejected even if
#               consumed_at is NULL (RESEARCH.md Pattern 2).
# consumed_at:  one-shot guard; NULL = not yet consumed; non-NULL = already used.
#               Atomic UPDATE ... WHERE consumed_at IS NULL RETURNING fingerprint
#               ensures "first wins" under concurrent bind attempts.
_CREATE_PAIRING_CODES = (
    "CREATE TABLE IF NOT EXISTS gruvax.pairing_codes ("
    "  code CHAR(4) PRIMARY KEY,"
    "  fingerprint TEXT NOT NULL,"
    "  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
    "  expires_at TIMESTAMPTZ NOT NULL,"
    "  consumed_at TIMESTAMPTZ"
    ")"
)


# ── INDEXES: gruvax.devices ───────────────────────────────────────────────────

# Partial-unique index on active (non-revoked) fingerprints.
# Guarantees at most one active row per fingerprint — prevents a device from being
# "paired twice" while still active. The partial predicate matches the per-request
# lookup WHERE revoked_at IS NULL (D3-07 fast path).
_IDX_DEVICES_FP_ACTIVE = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_devices_fingerprint_active"
    " ON gruvax.devices (fingerprint)"
    " WHERE revoked_at IS NULL"
)

# Plain non-partial index on all fingerprints (active + revoked).
# Required because the revoke-guard query reads:
#   SELECT id, profile_id, revoked_at FROM gruvax.devices WHERE fingerprint = %s
# WITHOUT a partial predicate — it must find revoked rows to return 403 "device_revoked".
# The partial-unique index above is NOT usable for this query (the query's WHERE clause
# does not match the index predicate). Cost is negligible at household scale.
# (RESEARCH.md Pitfall 5 / Open Question 2)
_IDX_DEVICES_FP_PLAIN = (
    "CREATE INDEX IF NOT EXISTS idx_devices_fingerprint"
    " ON gruvax.devices (fingerprint)"
)

# Partial-unique index on active (non-revoked), non-orphaned profile assignments.
# Guarantees at most one active device per profile_id when profile_id IS NOT NULL.
# NULL profile_id rows (orphaned devices) are excluded from the uniqueness constraint
# so multiple orphaned devices can coexist waiting for admin reassignment.
_IDX_DEVICES_PROFILE_ACTIVE = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_devices_profile_active"
    " ON gruvax.devices (profile_id)"
    " WHERE revoked_at IS NULL AND profile_id IS NOT NULL"
)


# ── INDEXES: gruvax.pairing_codes ────────────────────────────────────────────

# Plain index on expires_at for TTL-based cleanup queries and expired-code checks.
# The bind endpoint filters: WHERE consumed_at IS NULL AND expires_at > NOW()
# so this index assists the range scan on expires_at at query time.
_IDX_PAIRING_CODES_EXPIRES = (
    "CREATE INDEX IF NOT EXISTS idx_pairing_codes_expires"
    " ON gruvax.pairing_codes (expires_at)"
)


# ── DOWNGRADE: drop indexes then tables in reverse dependency order ───────────
# Indexes must be dropped before their tables. Tables in reverse creation order.
# DROP INDEX uses schema-qualified name (idx lives in gruvax schema because the
# table is in gruvax schema and no explicit schema was given in CREATE INDEX ON
# gruvax.devices — Postgres places the index in the same schema as the table).
_DROP_IDX_PAIRING_CODES_EXPIRES = "DROP INDEX IF EXISTS gruvax.idx_pairing_codes_expires"
_DROP_IDX_DEVICES_PROFILE_ACTIVE = "DROP INDEX IF EXISTS gruvax.idx_devices_profile_active"
_DROP_IDX_DEVICES_FP_PLAIN = "DROP INDEX IF EXISTS gruvax.idx_devices_fingerprint"
_DROP_IDX_DEVICES_FP_ACTIVE = "DROP INDEX IF EXISTS gruvax.idx_devices_fingerprint_active"
_DROP_TABLE_PAIRING_CODES = "DROP TABLE IF EXISTS gruvax.pairing_codes"
_DROP_TABLE_DEVICES = "DROP TABLE IF EXISTS gruvax.devices"


def upgrade() -> None:
    # 1. Create tables (devices first — pairing_codes references its fingerprint
    #    conceptually but not via FK, so order is arbitrary; devices first is cleaner).
    op.execute(_CREATE_DEVICES)
    op.execute(_CREATE_PAIRING_CODES)

    # 2. Create indexes (after tables exist).
    op.execute(_IDX_DEVICES_FP_ACTIVE)
    op.execute(_IDX_DEVICES_FP_PLAIN)
    op.execute(_IDX_DEVICES_PROFILE_ACTIVE)
    op.execute(_IDX_PAIRING_CODES_EXPIRES)


def downgrade() -> None:
    # Reverse order: indexes first (Postgres would error dropping a table with
    # dependent indexes, though IF EXISTS makes this a no-op in practice), then
    # tables. pairing_codes first (no dependents), then devices.
    op.execute(_DROP_IDX_PAIRING_CODES_EXPIRES)
    op.execute(_DROP_IDX_DEVICES_PROFILE_ACTIVE)
    op.execute(_DROP_IDX_DEVICES_FP_PLAIN)
    op.execute(_DROP_IDX_DEVICES_FP_ACTIVE)
    op.execute(_DROP_TABLE_PAIRING_CODES)
    op.execute(_DROP_TABLE_DEVICES)

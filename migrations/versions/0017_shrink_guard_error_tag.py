"""Extend profiles.last_sync_error CHECK to allow 'shrink_guard' (gruvax-envc).

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-27

Bug gruvax-envc: the atomic swap in ``profile_sync._swap_inside_tx`` had no
guard against an upstream response that silently returns fewer rows than the
profile already has cached (e.g. discogsography's MATCH-not-MERGE collection
sync drops a release not yet present in the monthly data dump). The naive
``new_record_count = max(0, row_count - existing_count)`` formula clamps at
zero, so a shrinking sync reported ``status='ok'`` with ``new_record_count=0``
— indistinguishable from "no new records" at every layer, and the newest
(most likely to be searched) records silently vanished from the kiosk.

The fix (``profile_sync.ShrinkGuardTripped``) aborts the swap transaction
when the incoming collection would shrink the cache by more than a tolerated
fraction, tagging the failure ``last_sync_error='shrink_guard'`` so it's
visible in admin diagnostics instead of being indistinguishable from success.
That tag isn't in the migration-0009 CHECK constraint's allowed set, so this
migration adds it.

Irreversibility note (carried from the 0013-0016 precedent): ``downgrade()``
deliberately does NOT re-tighten the CHECK constraint back to the pre-0017
value set. Once ANY row has been written with ``last_sync_error='shrink_guard'``
(a live, reachable production code path — not a hypothetical), re-adding the
old, narrower CHECK constraint on downgrade would raise a
``CheckViolation`` against that row's existing data — the exact same
data-shaped irreversibility 0013-0016 already accepted for their own
column changes. Leaving the wider CHECK in place on downgrade is safe: it
never rejects any value the pre-0017 schema would have accepted, so no
tooling written against the OLD schema's contract is broken by the extra
tolerance.

Conventions (carried from 0001-0016): all DDL via op.execute() with explicit
statements.
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | None = None
depends_on: str | None = None

_NEW_CHECK = (
    "last_sync_error IN "
    "('pat_rejected','network','rate_limited','server_error','cancelled','shrink_guard')"
    " OR last_sync_error IS NULL"
)


def upgrade() -> None:
    op.execute("ALTER TABLE gruvax.profiles DROP CONSTRAINT profiles_last_sync_error_check")
    op.execute(
        f"ALTER TABLE gruvax.profiles ADD CONSTRAINT profiles_last_sync_error_check "
        f"CHECK ({_NEW_CHECK})"
    )


def downgrade() -> None:
    # No-op: no schema to safely reverse (see Irreversibility note above). Once
    # 'shrink_guard' data exists, re-adding the narrower CHECK would fail on
    # that data — the same lossy-backfill precedent set by migrations
    # 0013-0016. Leaving the wider CHECK in place is a strict superset of the
    # pre-0017 contract, so it breaks nothing that relied on the old shape.
    pass

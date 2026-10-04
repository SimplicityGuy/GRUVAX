"""Preservation guard for rollback to the single-profile schema.

Locks are transaction-owned and held until the whole migration chain completes.
A profile row alone carries user metadata/PAT and must prevent destructive rollback.
"""

PROFILE_DOWNGRADE_GUARD = """
LOCK TABLE gruvax.profiles, gruvax.profile_collection,
    gruvax.admin_sessions, gruvax.boundary_history, gruvax.cube_boundaries,
    gruvax.idempotency_keys, gruvax.record_stats, gruvax.segment_overrides,
    gruvax.settings IN ACCESS EXCLUSIVE MODE;
DO $$
BEGIN
    IF EXISTS (
        SELECT id FROM gruvax.profiles
        WHERE id != '00000000-0000-0000-0000-000000000001'::uuid
    ) OR EXISTS (
        SELECT 1 FROM (
        SELECT profile_id FROM gruvax.profile_collection
        UNION ALL SELECT profile_id FROM gruvax.admin_sessions
        UNION ALL SELECT profile_id FROM gruvax.boundary_history
        UNION ALL SELECT profile_id FROM gruvax.cube_boundaries
        UNION ALL SELECT profile_id FROM gruvax.idempotency_keys
        UNION ALL SELECT profile_id FROM gruvax.record_stats
        UNION ALL SELECT profile_id FROM gruvax.segment_overrides
        UNION ALL SELECT profile_id FROM gruvax.settings
        ) AS owned_rows
        WHERE profile_id != '00000000-0000-0000-0000-000000000001'::uuid
    ) THEN
        RAISE EXCEPTION 'Cannot downgrade: non-default profile data would be lost; export and preserve it before retrying'
            USING ERRCODE = '55000';
    END IF;
END $$;
"""


# Writers acquire record_stats before history. Keep that order here and hold
# both table locks through the atomic chain, including the subsequent DROP.
ACTIVITY_DOWNGRADE_GUARD = """
LOCK TABLE gruvax.record_stats, gruvax.record_activity IN ACCESS EXCLUSIVE MODE;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM gruvax.record_activity
        WHERE occurred_at > now() - INTERVAL '168 hours'
    ) THEN
        RAISE EXCEPTION 'Cannot downgrade: recent record activity would be lost; preserve the history or wait until its seven-day window expires'
            USING ERRCODE = '55000';
    END IF;
END $$;
"""


SNAPSHOT_ERROR_DOWNGRADE_GUARD = """
LOCK TABLE gruvax.profiles IN ACCESS EXCLUSIVE MODE;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM gruvax.profiles WHERE last_sync_error = 'snapshot_mismatch') THEN
        RAISE EXCEPTION 'Cannot downgrade: snapshot mismatch status would be lost; preserve affected profile state before retrying'
            USING ERRCODE = '55000';
    END IF;
END $$;
"""

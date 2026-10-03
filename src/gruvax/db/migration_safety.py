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

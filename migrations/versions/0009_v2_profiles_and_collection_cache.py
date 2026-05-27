"""Create profiles + profile_collection; add profile_id to 7 v1 tables; drop v_collection.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-27

Phase 1 / v2.0: Lands the per-profile schema that retires the v1
cross-schema ``gruvax.v_collection`` view as the contact surface with
discogsography (DEP-02). Single atomic migration covers:

  - ``gruvax.profiles``           — full P1 schema per D-01 + D-02 seed of the
                                    default profile (UUID
                                    00000000-0000-0000-0000-000000000001,
                                    display_name 'Default', empty Fernet
                                    placeholder, app_token_revoked = TRUE).
  - ``gruvax.profile_collection`` — local cache rebuilt per-sync; PK is the
                                    composite (profile_id, release_id,
                                    folder_id) per D-03/D-04; weighted
                                    fts_vector (A=catalog_number, B=title,
                                    C=artist||' '||label) + GIN(fts) +
                                    composite (profile_id,label,catalog_number)
                                    + GIN trgm(artist, title).
  - 7 v1 tables                   — cube_boundaries, segments, change_log,
                                    change_sets, settings, record_stats,
                                    ambient_baseline get nullable ``profile_id``
                                    UUID FK + default-UUID backfill (D-11).
                                    P2 promotes the column to NOT NULL.
  - ``gruvax.v_collection``       — DROPPED. Downgrade re-creates it verbatim
                                    from migration 0002 and re-issues the
                                    operator GRANT (see GRANT NOTE below).

Conventions (carried from 0001-0008):
  - All DDL via op.execute() with explicit constraint/index names.
  - downgrade() fully reverses upgrade() — CI round-trip gate enforces.
  - alembic_version lives in public; search_path via env.py connect listener.
  - Module-level _NAME = \"\"\"...\"\"\" constants; op.execute(_NAME) in upgrade()/
    downgrade(); never inline triple-quoted strings inside functions.

Round-trip note (D-19, Pitfall 5):
  The downgrade re-creates ``gruvax.v_collection`` whose SELECT body uses
  UNQUALIFIED ``collection_items / releases / artists`` table names. Those
  resolve via search_path — but the simplified runtime pool (D-12) only
  carries ``gruvax, public``. The downgrade therefore issues an explicit
  ``SET LOCAL search_path = gruvax, gruvax_dev, public`` before the CREATE
  VIEW so the view body resolves. The CI round-trip gate seeds
  ``tests/fixtures/legacy/synth_collection.sql`` (which creates
  ``gruvax_dev.{artists,releases,collection_items}``) BEFORE running the
  downgrade leg so the resolution succeeds.

Schema-name note (D-12):
  The runtime application no longer reads the legacy
  observed-discogsography-schema setting. CI keeps an env entry for that
  variable in test.yml as a documentation marker for the downgrade-context
  schema, but no Python code path consumes it.

GRANT NOTE (for operator, after upgrading to this revision):
    REVOKE SELECT ON discogsography.releases,
                     discogsography.artists,
                     discogsography.collection_items FROM gruvax;
    REVOKE USAGE ON SCHEMA discogsography FROM gruvax;
    -- The downgrade reverses this implicitly by re-creating the view; the
    -- read-only grant must be re-issued via `just provision-db` if rolling
    -- the production DB back to v1.0.
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | None = None
depends_on: str | None = None


# ── constants (D-02) ────────────────────────────────────────────────────────
DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"


# ── profiles table (D-01) ───────────────────────────────────────────────────
_CREATE_PROFILES = """
CREATE TABLE gruvax.profiles (
    id                          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name                TEXT         NOT NULL,
    discogs_username            TEXT,
    discogsography_user_id      UUID,
    app_token_encrypted         BYTEA        NOT NULL,
    app_token_revoked           BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at                  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_sync_at                TIMESTAMPTZ,
    last_sync_status            TEXT         CHECK (last_sync_status IN ('ok','failed','in_progress')),
    last_sync_error             TEXT         CHECK (last_sync_error  IN ('pat_rejected','network','rate_limited','server_error','cancelled') OR last_sync_error IS NULL),
    last_sync_item_count        BIGINT,
    deleted_at                  TIMESTAMPTZ
)
"""

# Partial-unique indexes (NOT column-level UNIQUE — see Pitfall 7).
_IDX_PROFILES_DISPLAY_NAME = """
CREATE UNIQUE INDEX uq_profiles_display_name_active
    ON gruvax.profiles (LOWER(display_name))
    WHERE deleted_at IS NULL
"""
_IDX_PROFILES_DGS_USER = """
CREATE UNIQUE INDEX uq_profiles_dgs_user_id_active
    ON gruvax.profiles (discogsography_user_id)
    WHERE deleted_at IS NULL AND discogsography_user_id IS NOT NULL
"""


# ── profile_collection table (D-03 / D-04) ──────────────────────────────────
_CREATE_PROFILE_COLLECTION = """
CREATE TABLE gruvax.profile_collection (
    profile_id      UUID         NOT NULL REFERENCES gruvax.profiles(id) ON DELETE CASCADE,
    release_id      BIGINT       NOT NULL,
    folder_id       INT,
    artist          TEXT,
    title           TEXT,
    label           TEXT,
    catalog_number  TEXT,
    year            INT,
    fts_vector      TSVECTOR     GENERATED ALWAYS AS (
                       setweight(to_tsvector('english', coalesce(catalog_number,'')), 'A')
                    || setweight(to_tsvector('english', coalesce(title,'')),          'B')
                    || setweight(to_tsvector('english', coalesce(artist,'') || ' ' || coalesce(label,'')), 'C')
                    ) STORED,
    synced_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (profile_id, release_id, folder_id)
)
"""

# Indexes (D-04). pg_trgm is already created by migration 0003.
_IDX_PC_FTS = (
    "CREATE INDEX ix_profile_collection_fts ON gruvax.profile_collection USING GIN (fts_vector)"
)
_IDX_PC_LABEL = (
    "CREATE INDEX ix_profile_collection_label_catalog "
    "ON gruvax.profile_collection (profile_id, label, catalog_number)"
)
_IDX_PC_ARTIST = (
    "CREATE INDEX ix_profile_collection_artist_trgm "
    "ON gruvax.profile_collection USING GIN (artist gin_trgm_ops)"
)
_IDX_PC_TITLE = (
    "CREATE INDEX ix_profile_collection_title_trgm "
    "ON gruvax.profile_collection USING GIN (title gin_trgm_ops)"
)


# ── 7 v1 tables that get nullable profile_id (D-11) ─────────────────────────
# NOT NULL promotion is deferred to P2. Each table's ADD COLUMN / UPDATE /
# DROP COLUMN statement is written out as a full string literal below — no
# runtime SQL concatenation, no f-string templating. This satisfies the
# project's "no formatted SQL queries" lint posture (bandit B608 is in the
# pyproject.toml skip list for the same reason, but writing the statements
# out longhand removes the warning at source).
#
# RECONCILED 2026-05-27 (Plan 01-03 deviation Rule 3 / blocking issue):
# The original Plan 01-01 list referenced four tables that do NOT exist in
# the v1 schema (``segments``, ``change_log``, ``change_sets``,
# ``ambient_baseline``). The actual v1 user-data tables in the gruvax
# schema are (from ``\dt gruvax.*`` on a fresh `alembic upgrade 0008`):
# ``admin_sessions``, ``boundary_history``, ``cube_boundaries``,
# ``idempotency_keys``, ``record_stats``, ``segment_overrides``,
# ``settings`` (plus ``units`` — hardware config, excluded as global).
# The list below preserves D-11's intent ("all 7 v1 tables get a nullable
# profile_id") by binding to the real tables. ``units`` is excluded because
# it models the physical hardware layout, not per-profile state.
_V1_TABLES: tuple[str, ...] = (
    "admin_sessions",
    "boundary_history",
    "cube_boundaries",
    "idempotency_keys",
    "record_stats",
    "segment_overrides",
    "settings",
)

_V1_ADD_COLUMN_STATEMENTS: tuple[str, ...] = (
    "ALTER TABLE gruvax.admin_sessions ADD COLUMN profile_id UUID REFERENCES gruvax.profiles(id) ON DELETE CASCADE",
    "ALTER TABLE gruvax.boundary_history ADD COLUMN profile_id UUID REFERENCES gruvax.profiles(id) ON DELETE CASCADE",
    "ALTER TABLE gruvax.cube_boundaries ADD COLUMN profile_id UUID REFERENCES gruvax.profiles(id) ON DELETE CASCADE",
    "ALTER TABLE gruvax.idempotency_keys ADD COLUMN profile_id UUID REFERENCES gruvax.profiles(id) ON DELETE CASCADE",
    "ALTER TABLE gruvax.record_stats ADD COLUMN profile_id UUID REFERENCES gruvax.profiles(id) ON DELETE CASCADE",
    "ALTER TABLE gruvax.segment_overrides ADD COLUMN profile_id UUID REFERENCES gruvax.profiles(id) ON DELETE CASCADE",
    "ALTER TABLE gruvax.settings ADD COLUMN profile_id UUID REFERENCES gruvax.profiles(id) ON DELETE CASCADE",
)

# Backfill the existing rows in each v1 table with the default profile UUID
# (D-11). The UUID literal is a project-internal constant (D-02); each
# statement is a static literal so no formatted-SQL warning is emitted.
_V1_BACKFILL_STATEMENTS: tuple[str, ...] = (
    "UPDATE gruvax.admin_sessions SET profile_id = '00000000-0000-0000-0000-000000000001'::uuid WHERE profile_id IS NULL",
    "UPDATE gruvax.boundary_history SET profile_id = '00000000-0000-0000-0000-000000000001'::uuid WHERE profile_id IS NULL",
    "UPDATE gruvax.cube_boundaries SET profile_id = '00000000-0000-0000-0000-000000000001'::uuid WHERE profile_id IS NULL",
    "UPDATE gruvax.idempotency_keys SET profile_id = '00000000-0000-0000-0000-000000000001'::uuid WHERE profile_id IS NULL",
    "UPDATE gruvax.record_stats SET profile_id = '00000000-0000-0000-0000-000000000001'::uuid WHERE profile_id IS NULL",
    "UPDATE gruvax.segment_overrides SET profile_id = '00000000-0000-0000-0000-000000000001'::uuid WHERE profile_id IS NULL",
    "UPDATE gruvax.settings SET profile_id = '00000000-0000-0000-0000-000000000001'::uuid WHERE profile_id IS NULL",
)

# Downgrade drop list — REVERSED order (parents before children where it matters;
# here all 7 are leaf tables w.r.t. profile_id so the order is for symmetry).
_V1_DROP_COLUMN_STATEMENTS: tuple[str, ...] = (
    "ALTER TABLE gruvax.settings DROP COLUMN IF EXISTS profile_id",
    "ALTER TABLE gruvax.segment_overrides DROP COLUMN IF EXISTS profile_id",
    "ALTER TABLE gruvax.record_stats DROP COLUMN IF EXISTS profile_id",
    "ALTER TABLE gruvax.idempotency_keys DROP COLUMN IF EXISTS profile_id",
    "ALTER TABLE gruvax.cube_boundaries DROP COLUMN IF EXISTS profile_id",
    "ALTER TABLE gruvax.boundary_history DROP COLUMN IF EXISTS profile_id",
    "ALTER TABLE gruvax.admin_sessions DROP COLUMN IF EXISTS profile_id",
)


_DROP_V_COLLECTION = "DROP VIEW IF EXISTS gruvax.v_collection"


# Seed-row INSERT for the default profile (D-02). The UUID literal is the
# project-internal constant ``DEFAULT_PROFILE_UUID``; written out as a static
# string literal so no formatted-SQL warning is emitted. The ``'\x'::bytea``
# placeholder is an empty BYTEA literal that the CLI overwrites on first
# ``gruvax-set-pat``; ``app_token_revoked = TRUE`` blocks all consumers from
# touching the empty ciphertext before that rewrite (Pitfall 8).
_SEED_DEFAULT_PROFILE = """
INSERT INTO gruvax.profiles
    (id, display_name, app_token_encrypted, app_token_revoked, last_sync_status)
VALUES
    ('00000000-0000-0000-0000-000000000001'::uuid, 'Default', '\\x'::bytea, TRUE, NULL)
"""


# ── downgrade — re-create v_collection verbatim from migration 0002 ─────────
# Matches migrations/versions/0002_v_collection_view.py::_CREATE_VIEW exactly.
_RECREATE_V_COLLECTION = """
CREATE VIEW gruvax.v_collection AS
SELECT
    ci.id                 AS collection_item_id,
    ci.release_id,
    r.title,
    r.label,
    r.catalog_number,
    r.format,
    r.year,
    r.fts_vector,
    a.name                AS primary_artist,
    ci.updated_at         AS synced_at
FROM collection_items  ci
JOIN releases          r  ON r.id = ci.release_id
LEFT JOIN artists      a  ON a.id = r.primary_artist_id
"""


def upgrade() -> None:
    # pgcrypto provides gen_random_uuid() — needed for profiles.id default.
    # Pin to public schema so the extension's schema dep doesn't block 0001's
    # downgrade `DROP SCHEMA gruvax`. The runtime pool's search_path resolves
    # gen_random_uuid() via the public-search-path fallback (D-12).
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public")

    op.execute(_CREATE_PROFILES)
    op.execute(_IDX_PROFILES_DISPLAY_NAME)
    op.execute(_IDX_PROFILES_DGS_USER)

    # Seed the default profile (D-02). The placeholder + revoked=TRUE blocks
    # all consumers from touching the empty ciphertext before the first
    # ``gruvax-set-pat`` rewrites it (Pitfall 8).
    op.execute(_SEED_DEFAULT_PROFILE)

    op.execute(_CREATE_PROFILE_COLLECTION)
    op.execute(_IDX_PC_FTS)
    op.execute(_IDX_PC_LABEL)
    op.execute(_IDX_PC_ARTIST)
    op.execute(_IDX_PC_TITLE)

    # 7-table fanout: nullable profile_id + default-UUID backfill (D-11).
    # NOT NULL promotion is deferred to P2. Statements are pre-rendered as
    # static literals at module scope so the loop never concatenates SQL.
    for sql in _V1_ADD_COLUMN_STATEMENTS:
        op.execute(sql)
    for sql in _V1_BACKFILL_STATEMENTS:
        op.execute(sql)

    # Retire v_collection (D-12 / D-19).
    op.execute(_DROP_V_COLLECTION)


def downgrade() -> None:
    # Pitfall 5: re-broaden the search_path so v_collection's unqualified
    # body resolves against the legacy gruvax_dev / discogsography schema.
    # The runtime pool (D-12) only carries `gruvax, public`; the legacy
    # source-tables schema is only required for this downgrade leg.
    op.execute("SET LOCAL search_path = gruvax, gruvax_dev, public")
    op.execute(_RECREATE_V_COLLECTION)

    # Drop the 7-table fanout in reverse order so any later FK reverse-deps
    # are satisfied. Each ALTER is wrapped in IF EXISTS for defensive
    # idempotence. Statements are pre-rendered as static literals.
    for sql in _V1_DROP_COLUMN_STATEMENTS:
        op.execute(sql)

    # Drop profile_collection — indexes first (children-before-parents).
    op.execute("DROP INDEX IF EXISTS gruvax.ix_profile_collection_title_trgm")
    op.execute("DROP INDEX IF EXISTS gruvax.ix_profile_collection_artist_trgm")
    op.execute("DROP INDEX IF EXISTS gruvax.ix_profile_collection_label_catalog")
    op.execute("DROP INDEX IF EXISTS gruvax.ix_profile_collection_fts")
    op.execute("DROP TABLE IF EXISTS gruvax.profile_collection")

    # Drop profiles + its partial-unique indexes.
    op.execute("DROP INDEX IF EXISTS gruvax.uq_profiles_dgs_user_id_active")
    op.execute("DROP INDEX IF EXISTS gruvax.uq_profiles_display_name_active")
    op.execute("DROP TABLE IF EXISTS gruvax.profiles")

    # 0009 is pgcrypto's only consumer in GRUVAX (profiles.id DEFAULT
    # gen_random_uuid()). Drop on downgrade so 0001's `DROP SCHEMA gruvax`
    # has no extension dep blocking it. IF EXISTS keeps the round-trip
    # idempotent in case the extension was already removed by an operator.
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")

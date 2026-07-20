"""Accent-insensitive FTS: unaccent text-search config for the fts_vector column.

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-17

Bug gruvax-w4a7: the stored ``fts_vector`` generated column (migration 0009)
and the query-time ``websearch_to_tsquery`` both used the bare
``to_tsvector('english', ...)`` config, which PRESERVES accents.  An ASCII
kiosk keyboard cannot type é/ö, so the ASCII spelling is the only possible
query — and it silently missed accented records:

    to_tsvector('english','Beyoncé')      -> 'beyoncé'
    websearch_to_tsquery('english','Beyonce') -> 'beyonc'   (no @@ match)

Fix: install the ``unaccent`` extension and create a dedicated text-search
configuration ``gruvax.gruvax_fts`` that folds accents (``unaccent``
dictionary) BEFORE stemming (``english_stem``).  Both the stored generated
column and the query-time tsquery use it, so accented storage and ASCII
queries fold to the same lexemes: 'Björk'/'Bjork' -> 'bjork',
'Mötley Crüe'/'Motley Crue' -> 'motley'+'crue', 'Beyoncé'/'Beyonce' ->
'beyonce'.

Immutability note (why a custom config, not ``unaccent()`` inline):
  ``unaccent(text)`` is STABLE, so it cannot appear in a GENERATED column or
  a functional GIN index.  ``to_tsvector(regconfig, text)`` is IMMUTABLE even
  when the config's dictionary chain includes unaccent — the accent folding
  happens inside the tsvector machinery.  This is the documented
  PostgreSQL pattern for accent-insensitive FTS indexes.

Conventions (carried from 0001-0012):
  - All DDL via op.execute() with module-level _NAME constants.
  - downgrade() fully reverses upgrade() — CI round-trip gate enforces.
  - The config is schema-qualified (gruvax.gruvax_fts) so it resolves in both
    the generated-column expression and the runtime pool (search_path
    gruvax, public).
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | None = None
depends_on: str | None = None


# ── unaccent extension + custom text-search configuration ────────────────────
# Pin unaccent to public (mirrors 0009's pgcrypto placement) so the schema
# dependency does not block 0001's ``DROP SCHEMA gruvax`` downgrade.
_CREATE_UNACCENT = "CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA public"

# Fresh copy of the english config, then prepend the unaccent dictionary to the
# word/hword token mappings so accents are folded before english_stem runs.
_DROP_CONFIG = "DROP TEXT SEARCH CONFIGURATION IF EXISTS gruvax.gruvax_fts"
_CREATE_CONFIG = "CREATE TEXT SEARCH CONFIGURATION gruvax.gruvax_fts ( COPY = pg_catalog.english )"
_ALTER_MAPPING = """
ALTER TEXT SEARCH CONFIGURATION gruvax.gruvax_fts
    ALTER MAPPING FOR hword, hword_part, word
    WITH public.unaccent, english_stem
"""


# ── rebuild the fts_vector generated column against the new config ───────────
# Dropping the column also drops its dependent GIN index; both are recreated.
_DROP_FTS_COLUMN = "ALTER TABLE gruvax.profile_collection DROP COLUMN fts_vector"

_ADD_FTS_COLUMN_UNACCENT = """
ALTER TABLE gruvax.profile_collection
    ADD COLUMN fts_vector TSVECTOR GENERATED ALWAYS AS (
           setweight(to_tsvector('gruvax.gruvax_fts', coalesce(catalog_number,'')), 'A')
        || setweight(to_tsvector('gruvax.gruvax_fts', coalesce(title,'')),          'B')
        || setweight(to_tsvector('gruvax.gruvax_fts', coalesce(artist,'') || ' ' || coalesce(label,'')), 'C')
    ) STORED
"""

_ADD_FTS_COLUMN_ENGLISH = """
ALTER TABLE gruvax.profile_collection
    ADD COLUMN fts_vector TSVECTOR GENERATED ALWAYS AS (
           setweight(to_tsvector('english', coalesce(catalog_number,'')), 'A')
        || setweight(to_tsvector('english', coalesce(title,'')),          'B')
        || setweight(to_tsvector('english', coalesce(artist,'') || ' ' || coalesce(label,'')), 'C')
    ) STORED
"""

_CREATE_FTS_INDEX = (
    "CREATE INDEX ix_profile_collection_fts ON gruvax.profile_collection USING GIN (fts_vector)"
)


def upgrade() -> None:
    op.execute(_CREATE_UNACCENT)
    op.execute(_DROP_CONFIG)
    op.execute(_CREATE_CONFIG)
    op.execute(_ALTER_MAPPING)

    # Rebuild the generated column + its GIN index against gruvax.gruvax_fts.
    op.execute(_DROP_FTS_COLUMN)
    op.execute(_ADD_FTS_COLUMN_UNACCENT)
    op.execute(_CREATE_FTS_INDEX)


def downgrade() -> None:
    # Restore the plain 'english' generated column + index, then drop the config.
    op.execute(_DROP_FTS_COLUMN)
    op.execute(_ADD_FTS_COLUMN_ENGLISH)
    op.execute(_CREATE_FTS_INDEX)
    op.execute(_DROP_CONFIG)
    # Leave the unaccent extension installed — it is harmless and idempotent
    # (re-upgrade uses CREATE EXTENSION IF NOT EXISTS).

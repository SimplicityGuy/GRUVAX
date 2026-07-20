"""Consistent catalog-number tokenization: separator-normalize the FTS A-weight.

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-17

Bug gruvax-yd92: PostgreSQL FTS tokenizes a hyphen as a numeric sign, so the
stored ``fts_vector`` generated column (migration 0009/0013) turned
``'BLP-1016'`` into the lexemes ``'blp'`` + ``'-1016'`` (a SIGNED INT) — the
bare number ``'1016'`` therefore did NOT match, while the space form
``'BLP 1016'`` (lexemes ``'blp'`` + ``'1016'``) did.  Result: hyphenated
catalog numbers (46.6% of the seeded collection) were silently omitted from
bare-number search — the exact ``catalog number → cube`` core value.

Fix: normalize the catalog separators to spaces BEFORE tokenizing, so
``'BLP-1016'``, ``'BLP 1016'`` (and any ``[\\s\\-_./]`` separator run) all
tokenize to ``'blp'`` + ``'1016'``.  The ``[\\s\\-_./]+`` class mirrors
``normalize_catalog``'s ``_SEP_COLLAPSE`` regex and the ``cat`` CTE's
separator-collapse in ``queries.py`` — one normalization authority across the
index and the query paths.

Why the query side (queries.py) needs no change:
  For a bare-number query the catalog branch tests
  ``(setweight(to_tsvector(catalog),'A') || setweight(fts_vector,'C')) @@ q``.
  Once ``fts_vector`` carries the ``'1016'`` lexeme (this migration), the
  combined vector matches ``'1016'`` via the C-weighted fts_vector component,
  so the hyphenated record is returned.  Hyphen/space/concat QUERY shapes
  remain covered by the existing ``cat`` CTE (separator-collapse prefix LIKE).
  The concat shape ``'BLP1016'`` stays a single lexeme — a distinct
  no-tokenization case out of this bug's scope.

Chain note: this revises 0013 (gruvax-w4a7) because it rebuilds the SAME
``fts_vector`` generated column and reuses that migration's
``gruvax.gruvax_fts`` (unaccent → english_stem) config.  It must be applied
after 0013 — the serial-merge order is w4a7 then yd92.

Conventions (carried from 0001-0013):
  - All DDL via op.execute() with module-level _NAME constants.
  - downgrade() restores the 0013 column definition exactly (accent-folded,
    but NOT separator-normalized) so the CI round-trip gate is byte-clean.
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | None = None
depends_on: str | None = None


_DROP_FTS_COLUMN = "ALTER TABLE gruvax.profile_collection DROP COLUMN fts_vector"

# Upgrade: A-weight catalog tokenized from a separator-normalized form so
# hyphenated/spaced catalog numbers share the same lexemes (gruvax-yd92).
_ADD_FTS_COLUMN_NORMALIZED = r"""
ALTER TABLE gruvax.profile_collection
    ADD COLUMN fts_vector TSVECTOR GENERATED ALWAYS AS (
           setweight(to_tsvector('gruvax.gruvax_fts', regexp_replace(coalesce(catalog_number,''), '[\s\-_./]+', ' ', 'g')), 'A')
        || setweight(to_tsvector('gruvax.gruvax_fts', coalesce(title,'')),          'B')
        || setweight(to_tsvector('gruvax.gruvax_fts', coalesce(artist,'') || ' ' || coalesce(label,'')), 'C')
    ) STORED
"""

# Downgrade: the 0013 definition (accent-folded, raw catalog tokenization).
_ADD_FTS_COLUMN_0013 = """
ALTER TABLE gruvax.profile_collection
    ADD COLUMN fts_vector TSVECTOR GENERATED ALWAYS AS (
           setweight(to_tsvector('gruvax.gruvax_fts', coalesce(catalog_number,'')), 'A')
        || setweight(to_tsvector('gruvax.gruvax_fts', coalesce(title,'')),          'B')
        || setweight(to_tsvector('gruvax.gruvax_fts', coalesce(artist,'') || ' ' || coalesce(label,'')), 'C')
    ) STORED
"""

_CREATE_FTS_INDEX = (
    "CREATE INDEX ix_profile_collection_fts ON gruvax.profile_collection USING GIN (fts_vector)"
)


def upgrade() -> None:
    # Dropping the column drops its dependent GIN index; both are recreated.
    op.execute(_DROP_FTS_COLUMN)
    op.execute(_ADD_FTS_COLUMN_NORMALIZED)
    op.execute(_CREATE_FTS_INDEX)


def downgrade() -> None:
    op.execute(_DROP_FTS_COLUMN)
    op.execute(_ADD_FTS_COLUMN_0013)
    op.execute(_CREATE_FTS_INDEX)

"""Backfill: NFKC-normalize existing profile_collection.catalog_number values.

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-19

Bug gruvax-rn7l.6 (supersedes gruvax-pjyz): sync ingest (``profile_sync.
_release_to_tuple``) stored ``catalog_number`` verbatim, so a full-width
catalog (e.g. "BLP-4195" typed as FULLWIDTH characters, U+FF22 U+FF2C
U+FF30 U+FF0D U+FF14 U+FF11 U+FF19 U+FF15) landed in the column with its
compatibility characters intact. The estimator's ``parse_key`` NFKC-folds on
every read and so was never fooled, but BOTH SQL-side search paths only fold
*case*, not width/compatibility form:

  - the ``fts_vector`` generated column (migrations 0013/0014) tokenizes via
    Postgres's ``gruvax.gruvax_fts`` config (unaccent -> english_stem), which
    does not perform Unicode NFKC folding;
  - the catalog LIKE path (``queries.py``'s ``lower(regexp_replace(...))``)
    likewise only lowercases.

So a full-width catalog was shelved at the geometrically-correct cube (the
estimator agreed with itself) yet was unfindable by any ASCII query typed on
the kiosk's keyboard through either search path.

Fix (paired with the ingest-side fix in ``profile_sync._release_to_tuple``,
which now NFKC-normalizes new rows via ``estimator.normalize.
normalize_catalog_storage`` before they are written): this migration
renormalizes every EXISTING ``catalog_number`` value already in
``gruvax.profile_collection`` so historical rows agree too.

Why NFKC only (not the estimator's fully-collapsed ``normalize_catalog`` key
form) — see ``normalize_catalog_storage``'s docstring for the full rationale;
in short: fully collapsing separators at storage time would defeat migration
0014's fix (hyphen/space -> single-space-before-tokenize so a hyphenated
catalog splits into two FTS lexemes) and would casefold a column every read
site displays verbatim. Postgres's built-in ``NORMALIZE(text, NFKC)`` SQL
function (PG13+) is used here so the backfill is native SQL, matching the
Python-side ``unicodedata.normalize("NFKC", ...)`` transform char-for-char.

Idempotent: the ``WHERE catalog_number IS NOT NULL AND catalog_number <>
normalize(catalog_number, NFKC)`` guard means a value already in NFKC form
(every row after the first run, and every row written by the now-fixed
ingest path) is left untouched — re-running this migration updates zero
rows. ``fts_vector`` is a ``GENERATED ... STORED`` column and recomputes
itself automatically from the new ``catalog_number`` value; no separate
statement is needed to refresh it.

Irreversibility note: like the 0013/0014/0015 precedent, this migration has
no schema to reverse — ``downgrade()`` is a documented no-op. NFKC-folding a
full-width catalog is lossy (the original compatibility characters are not
recoverable from the folded ASCII form), consistent with every prior lossy
data-only backfill in this chain; the CI round-trip gate
(``alembic upgrade head && downgrade base && upgrade head``) exercises
schema state, not data fidelity.

Conventions (carried from 0001-0015):
  - All DDL/DML via op.execute() with explicit statements.
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | None = None
depends_on: str | None = None


# Idempotent backfill: only rows whose stored value differs from its NFKC
# fold are touched, so a re-run (or a run against an already-clean table
# fed exclusively by the fixed ingest path) is a no-op.
_BACKFILL_NFKC = """
UPDATE gruvax.profile_collection
SET catalog_number = normalize(catalog_number, NFKC)
WHERE catalog_number IS NOT NULL
  AND catalog_number <> normalize(catalog_number, NFKC)
"""


def upgrade() -> None:
    op.execute(_BACKFILL_NFKC)


def downgrade() -> None:
    # No-op: no schema to reverse (see Irreversibility note above). The
    # NFKC data transform is not recoverable, matching the lossy-backfill
    # precedent set by migrations 0013/0014/0015.
    pass

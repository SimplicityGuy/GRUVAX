"""Create gruvax.v_collection — read-only contract over discogsography.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-20

The view body uses UNQUALIFIED table names (collection_items, releases,
artists) so the connection's search_path determines which source schema is
used:
  - Dev / CI:   search_path includes "gruvax_dev"   → gruvax_dev.releases etc.
  - Production: search_path includes "discogsography" → discogsography.releases etc.

No code path needs to branch on environment — the same view body works
everywhere.  This is the sole read-contact surface with discogsography (DEP-02).

GRANT NOTE (for operator, never run by application code):
    GRANT USAGE ON SCHEMA discogsography TO gruvax_app;
    GRANT SELECT ON discogsography.releases,
                    discogsography.artists,
                    discogsography.collection_items TO gruvax_app;
    -- No INSERT / UPDATE / DELETE granted.
    -- See `just provision-db` for the full provisioning script.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


# The view SELECT references unqualified table names so search_path resolves
# the source schema at query time — no schema qualifier must ever appear here.
_CREATE_VIEW = """
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

_DROP_VIEW = "DROP VIEW IF EXISTS gruvax.v_collection"


def upgrade() -> None:
    op.execute(_CREATE_VIEW)


def downgrade() -> None:
    # Drop view before 0001 drops the schema.
    op.execute(_DROP_VIEW)

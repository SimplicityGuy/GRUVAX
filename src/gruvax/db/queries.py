"""Database queries for GRUVAX.

All SQL uses psycopg parameterized placeholders ($1, $2, ...) — never
f-string interpolation of user input (T-01-07 SQLi protection).

Functions:
  - ``search_collection``:  FTS + normalized catalog# union search.
  - ``get_release_for_locate``: fetch label + catalog# for a release_id.
"""

from __future__ import annotations

import time
from typing import Any

from psycopg_pool import AsyncConnectionPool

# ── Search result shape ───────────────────────────────────────────────────────

SearchRow = dict[str, Any]


async def search_collection(
    pool: AsyncConnectionPool,    q: str,
    limit: int,
) -> tuple[list[SearchRow], float]:
    """Execute FTS + catalog-number union search over gruvax.v_collection.

    Two parallel search paths (RESEARCH §Pattern 1):

    Path A — FTS:
        ``fts_vector @@ websearch_to_tsquery('english', $1)``
        Scored by ``ts_rank_cd(fts_vector, query, 4)``.

    Path B — Catalog prefix:
        ``lower(regexp_replace(catalog_number, '[\\s\\-_./]+', '', 'g'))
          LIKE lower(regexp_replace($1, ...)) || '%'``
        Fixed score 0.9 (reliably hits ``BLP 4195`` from ``blp4195``).

    The separator-collapse pattern ``[\\s\\-_./]+`` mirrors
    ``normalize_catalog``'s ``_SEP_COLLAPSE`` regex so ``blp4195``,
    ``BLP-4195``, and ``BLP 4195`` all match the same record.

    Results are de-duplicated via ``DISTINCT ON (release_id)`` and
    ordered by ``GREATEST(fts_score, cat_score) DESC``.

    Args:
        pool: Open psycopg ``AsyncConnectionPool``.
        q:    Raw user query string (already length-validated at router).
        limit: Max rows to return (already range-validated at router).

    Returns:
        A ``(rows, took_ms)`` tuple where ``rows`` is a list of dicts
        matching the ``SearchRow`` shape and ``took_ms`` is the wall-clock
        time for the DB round-trip in milliseconds.
    """
    # psycopg uses %s as the placeholder style (Python DB-API 2.0).
    # The query string itself uses %s; the (q, limit) tuple provides the values.
    # This is fully parameterized — q is never interpolated into SQL (T-01-07).
    sql = """
WITH fts AS (
    SELECT
        release_id,
        collection_item_id,
        title,
        primary_artist,
        label,
        catalog_number,
        format,
        year,
        ts_rank_cd(fts_vector, websearch_to_tsquery('english', %s), 4) AS score
    FROM gruvax.v_collection
    WHERE fts_vector @@ websearch_to_tsquery('english', %s)
    LIMIT 40
),
cat AS (
    SELECT
        release_id,
        collection_item_id,
        title,
        primary_artist,
        label,
        catalog_number,
        format,
        year,
        0.9::float AS score
    FROM gruvax.v_collection
    WHERE lower(regexp_replace(catalog_number, '[\\s\\-_./]+', '', 'g'))
          LIKE lower(regexp_replace(%s, '[\\s\\-_./]+', '', 'g')) || '%%'
    LIMIT 20
),
combined AS (
    SELECT
        COALESCE(fts.release_id, cat.release_id)           AS release_id,
        COALESCE(fts.collection_item_id, cat.collection_item_id) AS collection_item_id,
        COALESCE(fts.title, cat.title)                     AS title,
        COALESCE(fts.primary_artist, cat.primary_artist)   AS primary_artist,
        COALESCE(fts.label, cat.label)                     AS label,
        COALESCE(fts.catalog_number, cat.catalog_number)   AS catalog_number,
        COALESCE(fts.format, cat.format)                   AS format,
        COALESCE(fts.year, cat.year)                       AS year,
        GREATEST(
            COALESCE(fts.score, 0),
            COALESCE(cat.score, 0)
        ) AS rank
    FROM fts
    FULL OUTER JOIN cat USING (
        release_id, collection_item_id, title, primary_artist,
        label, catalog_number, format, year
    )
)
SELECT DISTINCT ON (release_id)
    release_id,
    collection_item_id,
    title,
    primary_artist,
    label,
    catalog_number,
    format,
    year,
    rank
FROM combined
ORDER BY release_id, rank DESC
LIMIT %s
"""
    t0 = time.perf_counter()
    async with pool.connection() as conn, conn.cursor() as cur:
        # q appears 3 times: FTS WHERE, FTS rank_cd, and catalog LIKE path.
        await cur.execute(sql, (q, q, q, limit))
        rows_raw = await cur.fetchall()
        # cursor.description gives column names
        cols = [desc[0] for desc in (cur.description or [])]
    took_ms = (time.perf_counter() - t0) * 1000.0

    rows: list[SearchRow] = [dict(zip(cols, row, strict=True)) for row in rows_raw]

    # Re-sort the de-duplicated rows by rank DESC (DISTINCT ON breaks ORDER BY)
    rows.sort(key=lambda r: r.get("rank", 0) or 0, reverse=True)
    return rows, took_ms


# ── Locate query ──────────────────────────────────────────────────────────────

LocateRecord = dict[str, Any]


async def get_release_for_locate(
    pool: AsyncConnectionPool,    release_id: int,
) -> LocateRecord | None:
    """Fetch label and catalog_number for a release_id from v_collection.

    Used by ``GET /api/locate`` to retrieve the record metadata needed to
    call the cube-only estimator.

    Args:
        pool:       Open psycopg pool.
        release_id: The Discogs release ID to look up (integer, already
                    validated at the router).

    Returns:
        A dict with keys ``release_id``, ``label``, ``catalog_number``,
        or ``None`` if the release_id is not in the collection.
    """
    sql = """
SELECT release_id, label, catalog_number
FROM gruvax.v_collection
WHERE release_id = %s
LIMIT 1
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, (release_id,))
        row = await cur.fetchone()

    if row is None:
        return None

    cols = ["release_id", "label", "catalog_number"]
    return dict(zip(cols, row, strict=True))

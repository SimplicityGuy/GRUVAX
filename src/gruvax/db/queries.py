"""Database queries for GRUVAX.

All SQL uses psycopg parameterized placeholders (%s) — never
f-string interpolation of user input (T-01-07 SQLi protection).

Functions:
  - ``search_collection``:     FTS + normalized catalog# union search with
                                catalog-number ranking boost (SRCH-08) and
                                did-you-mean lookup (SRCH-07).
  - ``get_release_for_locate``: fetch label + catalog# for a release_id.
  - ``is_catalog_query``:      pure helper — True when query looks like a
                                catalog number (D-12).
  - ``did_you_mean_query``:    async trigram-similarity suggestion when FTS
                                returns nothing strong (D-11).
  - ``load_settings_cache``:   load all key/value rows from gruvax.settings
                                into a dict for in-process caching (Phase 3).
"""

from __future__ import annotations

import re
import time
from typing import Any

import psycopg.errors
from psycopg_pool import AsyncConnectionPool

# ── Catalog-query detection regexes (D-12) ───────────────────────────────────
# Leading digit: "4195", "19BOX019", "1SHOT-002"
_LEADING_DIGIT = re.compile(r"^\d")
# Prefix + digits: "BLP 41", "ECM 10", "blp4195"
_PREFIX_DIGITS = re.compile(r"^[A-Za-z]+\s*\d")

# ── Did-you-mean threshold (D-11 — conservative) ─────────────────────────────
DID_YOU_MEAN_THRESHOLD: float = 0.35

# ── Search result shape ───────────────────────────────────────────────────────

SearchRow = dict[str, Any]


def is_catalog_query(q: str) -> bool:
    """Return True when *q* looks like a catalog-number query (D-12, SRCH-08).

    Matches two patterns (per RESEARCH §Pattern 2 — D-12):

    - Leading digit: ``4195``, ``19BOX019``, ``1SHOT-002``
    - Prefix + digits: ``BLP 41``, ``ECM 10``, ``blp4195``

    The stripped query is tested so leading/trailing whitespace is ignored.

    Args:
        q: Raw user query string.

    Returns:
        ``True`` when ``q`` matches a catalog-like pattern; ``False`` otherwise.
    """
    stripped = q.strip()
    return bool(_LEADING_DIGIT.match(stripped) or _PREFIX_DIGITS.match(stripped))


async def did_you_mean_query(
    pool: AsyncConnectionPool,
    q: str,
) -> str | None:
    """Return the top trigram-similarity match for *q* over label/artist terms.

    Runs only when FTS returned no results (D-11 — conservative).  Queries
    DISTINCT label and primary_artist values from ``gruvax.v_collection`` via
    ``pg_trgm similarity()``.

    Graceful degradation (Pitfall E): if ``similarity()`` is undefined (pg_trgm
    not installed), catches ``psycopg.errors.UndefinedFunction`` and returns
    ``None`` so the caller still receives a 200 response.

    All user input goes through ``%s`` placeholders — never f-string
    interpolation (T-01-07, T-02-06).

    Args:
        pool: Open psycopg ``AsyncConnectionPool``.
        q:    Raw user query string (already length-validated at router).

    Returns:
        The best-matching term string if similarity > threshold, else ``None``.
    """
    sql = """
SELECT term, similarity(term, %s) AS sim
FROM (
    SELECT DISTINCT label AS term
    FROM gruvax.v_collection
    WHERE label IS NOT NULL
    UNION
    SELECT DISTINCT primary_artist AS term
    FROM gruvax.v_collection
    WHERE primary_artist IS NOT NULL
) AS terms
WHERE similarity(term, %s) > %s
ORDER BY sim DESC
LIMIT 1
"""
    try:
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(sql, (q, q, DID_YOU_MEAN_THRESHOLD))
            row = await cur.fetchone()
        if row is None:
            return None
        return str(row[0])
    except psycopg.errors.UndefinedFunction:
        # pg_trgm not installed — degrade gracefully (Pitfall E)
        return None


async def search_collection(
    pool: AsyncConnectionPool,
    q: str,
    limit: int,
) -> tuple[list[SearchRow], float, str | None]:
    """Execute FTS + catalog-number union search over gruvax.v_collection.

    Two parallel search paths (RESEARCH §Pattern 1):

    Path A — FTS (with optional catalog boost):
        ``fts_vector @@ websearch_to_tsquery('english', %s)``
        Scored by ``ts_rank_cd(fts_vector, query, 4)``.
        When ``is_catalog_query(q)`` is True (SRCH-08/D-12), catalog_number
        tokens are re-weighted to 'A' (highest) so catalog matches rank above
        text matches.

    Path B — Catalog prefix:
        ``lower(regexp_replace(catalog_number, '[\\s\\-_./]+', '', 'g'))
          LIKE lower(regexp_replace(%s, ...)) || '%'``
        Fixed score 0.9 (reliably hits ``BLP 4195`` from ``blp4195``).

    The separator-collapse pattern ``[\\s\\-_./]+`` mirrors
    ``normalize_catalog``'s ``_SEP_COLLAPSE`` regex so ``blp4195``,
    ``BLP-4195``, and ``BLP 4195`` all match the same record.

    The two paths are combined with ``UNION ALL`` and de-duplicated via
    ``DISTINCT ON (release_id)`` keeping the highest-scoring row per release,
    then re-sorted by rank in Python.

    Did-you-mean (SRCH-07/D-11): when rows is empty (no strong FTS match),
    ``did_you_mean_query`` is called to find a high-trigram-similarity
    suggestion.  When pg_trgm is unavailable, this returns None gracefully
    (Pitfall E).

    Args:
        pool: Open psycopg ``AsyncConnectionPool``.
        q:    Raw user query string (already length-validated at router).
        limit: Max rows to return (already range-validated at router).

    Returns:
        A ``(rows, took_ms, did_you_mean)`` tuple where ``rows`` is a list of
        dicts matching the ``SearchRow`` shape, ``took_ms`` is the wall-clock
        time for the DB round-trip in milliseconds, and ``did_you_mean`` is a
        suggestion string (or None) returned only when ``rows`` is empty.
    """
    # SRCH-08: catalog-like queries boost catalog_number field weight.
    # setweight(to_tsvector('english', catalog_number), 'A') promotes catalog
    # tokens to the highest weight tier so ts_rank_cd scores them above body
    # text — catalog match ranks above text match for "BLP 4195".
    # All %s placeholders are fully parameterized (T-01-07, T-02-07).
    if is_catalog_query(q):
        sql = """
WITH fts AS (
    SELECT
        v.release_id,
        v.collection_item_id,
        v.title,
        v.primary_artist,
        v.label,
        v.catalog_number,
        v.format,
        v.year,
        ts_rank_cd(
            setweight(to_tsvector('english', coalesce(v.catalog_number, '')), 'A')
            || setweight(v.fts_vector, 'C'),
            tsq.query,
            4
        ) AS score
    FROM gruvax.v_collection v
    CROSS JOIN websearch_to_tsquery('english', %s) AS tsq(query)
    WHERE (
        setweight(to_tsvector('english', coalesce(v.catalog_number, '')), 'A')
        || setweight(v.fts_vector, 'C')
    ) @@ tsq.query
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
    SELECT release_id, collection_item_id, title, primary_artist,
           label, catalog_number, format, year, score
    FROM fts
    UNION ALL
    SELECT release_id, collection_item_id, title, primary_artist,
           label, catalog_number, format, year, score
    FROM cat
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
    score AS rank
FROM combined
ORDER BY release_id, score DESC
LIMIT %s
"""
    else:
        # Standard FTS path (non-catalog query).
        # psycopg uses %s as the placeholder style (Python DB-API 2.0).
        # The query string itself uses %s; the (q, limit) tuple provides the
        # values.  This is fully parameterized — q is never interpolated into
        # SQL (T-01-07).
        sql = """
WITH fts AS (
    -- websearch_to_tsquery is computed ONCE via the cross join (CR/WR-01),
    -- not twice (rank + WHERE). tsq.query is the single derived tsquery.
    SELECT
        v.release_id,
        v.collection_item_id,
        v.title,
        v.primary_artist,
        v.label,
        v.catalog_number,
        v.format,
        v.year,
        ts_rank_cd(v.fts_vector, tsq.query, 4) AS score
    FROM gruvax.v_collection v
    CROSS JOIN websearch_to_tsquery('english', %s) AS tsq(query)
    WHERE v.fts_vector @@ tsq.query
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
-- UNION ALL the two paths, then DISTINCT ON keeps the highest-scoring row
-- per release_id (CR-04).
combined AS (
    SELECT release_id, collection_item_id, title, primary_artist,
           label, catalog_number, format, year, score
    FROM fts
    UNION ALL
    SELECT release_id, collection_item_id, title, primary_artist,
           label, catalog_number, format, year, score
    FROM cat
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
    score AS rank
FROM combined
ORDER BY release_id, score DESC
LIMIT %s
"""

    t0 = time.perf_counter()
    async with pool.connection() as conn, conn.cursor() as cur:
        # q appears twice: FTS tsquery (cross join) and catalog LIKE path.
        await cur.execute(sql, (q, q, limit))
        rows_raw = await cur.fetchall()
        # cursor.description gives column names
        cols = [desc[0] for desc in (cur.description or [])]
    took_ms = (time.perf_counter() - t0) * 1000.0

    rows: list[SearchRow] = [dict(zip(cols, row, strict=True)) for row in rows_raw]

    # Re-sort the de-duplicated rows by rank DESC (DISTINCT ON breaks ORDER BY)
    rows.sort(key=lambda r: r.get("rank", 0) or 0, reverse=True)

    # SRCH-07 / D-11: only trigger did-you-mean when FTS finds nothing strong.
    did_you_mean: str | None = None
    if not rows:
        did_you_mean = await did_you_mean_query(pool, q)

    return rows, took_ms, did_you_mean


# ── Settings cache (Phase 3) ──────────────────────────────────────────────────


async def load_settings_cache(
    pool: AsyncConnectionPool,
) -> dict[str, Any]:
    """Load all rows from ``gruvax.settings`` into a key→value dict.

    Called once during FastAPI lifespan startup (step 3c) and stored in
    ``app.state.settings_cache``.  Provides nominal_capacity, idle TTL, and
    other Phase 3 runtime config without a per-request DB round-trip.

    Values are already JSONB-decoded by psycopg (numbers as int/float, strings
    as str, etc.).  Callers should use ``int(settings_cache.get("cube.nominal_capacity",
    95))`` to guard against a missing or malformed value.

    All SQL uses ``%s`` placeholders — no f-string interpolation (T-01-07).

    Args:
        pool: Open psycopg ``AsyncConnectionPool``.

    Returns:
        Dict mapping ``key`` (str) → decoded JSONB ``value`` for every row in
        ``gruvax.settings``.  Returns ``{}`` if the table is empty.
    """
    sql = "SELECT key, value FROM gruvax.settings"
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql)
        rows = await cur.fetchall()
    return {str(row[0]): row[1] for row in rows}


# ── Locate query ──────────────────────────────────────────────────────────────

LocateRecord = dict[str, Any]


async def get_release_for_locate(
    pool: AsyncConnectionPool,
    release_id: int,
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


# ── Admin boundary queries (Phase 3) ─────────────────────────────────────────

# Trigram threshold for boundary near-miss suggestions (D-07, ADMN-06).
# Slightly above DID_YOU_MEAN_THRESHOLD (0.35) — boundary validation is more
# context-specific and benefits from a tighter threshold.
# Configurable in gruvax.settings as boundary.near_miss_threshold (future).
BOUNDARY_TRGM_THRESHOLD: float = 0.40


async def find_boundary_near_misses(
    pool: AsyncConnectionPool,
    label: str,
    catalog: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return trigram near-misses for a phantom (label, catalog) pair.

    Queries ``gruvax.v_collection`` for the top ``limit`` rows whose label
    and/or catalog_number has similarity above ``BOUNDARY_TRGM_THRESHOLD`` to
    the provided inputs.  Uses a combined similarity score (average of label and
    catalog similarities) for ranking.

    Graceful degradation (Pitfall E — mirrors ``did_you_mean_query``):
    if ``similarity()`` is undefined (pg_trgm not installed), catches
    ``psycopg.errors.UndefinedFunction`` and returns [] so the caller still
    receives a valid response.

    All user input goes through ``%s`` placeholders — never f-string
    interpolation (T-01-07, T-03-16).

    Args:
        pool:    Open psycopg ``AsyncConnectionPool``.
        label:   Label from the proposed boundary value.
        catalog: Catalog number from the proposed boundary value.
        limit:   Maximum number of near-miss suggestions to return.

    Returns:
        List of dicts with keys ``label``, ``catalog_number``, ``similarity``.
        Empty list if pg_trgm is unavailable or no matches found.
    """
    sql = """
SELECT label, catalog_number,
       (similarity(lower(label), lower(%s)) * 0.5
        + similarity(lower(catalog_number), lower(%s)) * 0.5) AS sim
FROM gruvax.v_collection
WHERE similarity(lower(label), lower(%s)) > %s
   OR similarity(lower(catalog_number), lower(%s)) > %s
ORDER BY sim DESC
LIMIT %s
"""
    try:
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                sql,
                (
                    label,
                    catalog,  # combined score params
                    label,
                    BOUNDARY_TRGM_THRESHOLD,  # label WHERE
                    catalog,
                    BOUNDARY_TRGM_THRESHOLD,  # catalog WHERE
                    limit,
                ),
            )
            rows = await cur.fetchall()
        return [
            {
                "label": str(row[0]),
                "catalog_number": str(row[1]),
                "similarity": float(row[2]),
            }
            for row in rows
        ]
    except psycopg.errors.UndefinedFunction:
        # pg_trgm not installed — degrade gracefully (Pitfall E)
        return []


async def get_distinct_labels(pool: AsyncConnectionPool) -> list[str]:
    """Return all distinct labels present in gruvax.v_collection, sorted.

    Used by the admin cubes editor autocomplete to populate the label picker
    (D-06).  Source is exclusively v_collection (Pitfall 5 — never reads
    raw discogsography tables).

    All SQL uses %s placeholders (T-03-16).

    Args:
        pool: Open psycopg ``AsyncConnectionPool``.

    Returns:
        Sorted list of distinct label strings.
    """
    sql = """
SELECT DISTINCT label
FROM gruvax.v_collection
WHERE label IS NOT NULL
ORDER BY label
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql)
        rows = await cur.fetchall()
    return [str(row[0]) for row in rows]


async def get_catalogs_for_label(
    pool: AsyncConnectionPool,
    label: str,
) -> list[dict[str, Any]]:
    """Return all release_id + catalog_number for records with the given label.

    Used by the admin cubes editor autocomplete to populate the catalog# picker
    after a label has been selected (two-step dependent autocomplete, D-06).
    The label comparison is case-insensitive via lower().

    Source is exclusively v_collection (Pitfall 5).
    All SQL uses %s placeholders (T-03-16).

    Args:
        pool:  Open psycopg ``AsyncConnectionPool``.
        label: Label to filter by (matched case-insensitively).

    Returns:
        List of dicts with keys ``release_id`` (int) and ``catalog_number`` (str),
        ordered by catalog_number.
    """
    sql = """
SELECT release_id, catalog_number
FROM gruvax.v_collection
WHERE lower(label) = lower(%s)
ORDER BY catalog_number
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, (label,))
        rows = await cur.fetchall()
    return [{"release_id": int(row[0]), "catalog_number": str(row[1])} for row in rows]


# ── Admin bulk-write + history + idempotency queries (Phase 3 Plan 05) ────────


async def fetch_current_boundary(
    conn: Any,
    unit_id: int,
    row: int,
    col: int,
) -> dict[str, Any] | None:
    """Read the current boundary row for a cube using an existing connection.

    Used inside a transaction (atomic bulk write) to capture prev_* values
    before overwriting with new ones.  All SQL uses %s placeholders (T-03-24).

    Args:
        conn:    Open psycopg async connection (inside a transaction).
        unit_id: Cube unit ID.
        row:     Cube row index.
        col:     Cube column index.

    Returns:
        Dict with boundary fields or None if the cube does not exist.
    """
    sql = """
SELECT unit_id, row, col, first_label, first_catalog,
       last_label, last_catalog, is_empty
FROM gruvax.cube_boundaries
WHERE unit_id = %s AND row = %s AND col = %s
"""
    async with conn.cursor() as cur:
        await cur.execute(sql, (unit_id, row, col))
        row_raw = await cur.fetchone()
        if row_raw is None:
            return None
        cols_meta = [desc[0] for desc in (cur.description or [])]
        return dict(zip(cols_meta, row_raw, strict=True))


async def write_boundary(
    conn: Any,
    unit_id: int,
    row: int,
    col: int,
    first_label: str | None,
    first_catalog: str | None,
    last_label: str | None,
    last_catalog: str | None,
    is_empty: bool,
) -> None:
    """Update a cube's boundary values using an existing connection.

    Used inside a transaction — the caller is responsible for commit.
    All SQL uses %s placeholders (T-03-24, zero f-string interpolation).

    Args:
        conn:          Open psycopg async connection (inside a transaction).
        unit_id:       Cube unit ID.
        row:           Cube row index.
        col:           Cube column index.
        first_label:   New first boundary label.
        first_catalog: New first boundary catalog number.
        last_label:    New last boundary label.
        last_catalog:  New last boundary catalog number.
        is_empty:      Whether the cube is empty.
    """
    sql = """
UPDATE gruvax.cube_boundaries
SET first_label = %s, first_catalog = %s,
    last_label = %s, last_catalog = %s,
    is_empty = %s
WHERE unit_id = %s AND row = %s AND col = %s
"""
    await conn.execute(
        sql,
        (first_label, first_catalog, last_label, last_catalog, is_empty, unit_id, row, col),
    )


async def write_history_row(
    conn: Any,
    change_set_id: str,
    unit_id: int,
    row: int,
    col: int,
    prev: dict[str, Any] | None,
    new_first_label: str | None,
    new_first_catalog: str | None,
    new_last_label: str | None,
    new_last_catalog: str | None,
    new_is_empty: bool,
    source: str,
) -> None:
    """Append one row to boundary_history for a single cube change.

    source must be 'manual', 'bulk', or 'revert' (DB CHECK constraint).
    prev is None for cubes that had no prior boundary entry.
    All SQL uses %s placeholders (T-03-24).

    Args:
        conn:          Open psycopg async connection (inside a transaction).
        change_set_id: UUID shared across all cubes in one atomic commit.
        unit_id:       Cube unit ID.
        row:           Cube row index.
        col:           Cube column index.
        prev:          Dict with prev_* fields from fetch_current_boundary.
        new_*:         The new boundary values being written.
        source:        'manual', 'bulk', or 'revert'.
    """
    sql = """
INSERT INTO gruvax.boundary_history (
    change_set_id, unit_id, row, col,
    prev_first_label, prev_first_catalog, prev_last_label, prev_last_catalog, prev_is_empty,
    new_first_label, new_first_catalog, new_last_label, new_last_catalog, new_is_empty,
    source
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""
    prev_first_label = prev.get("first_label") if prev else None
    prev_first_catalog = prev.get("first_catalog") if prev else None
    prev_last_label = prev.get("last_label") if prev else None
    prev_last_catalog = prev.get("last_catalog") if prev else None
    prev_is_empty = bool(prev.get("is_empty", True)) if prev else True

    await conn.execute(
        sql,
        (
            change_set_id,
            unit_id,
            row,
            col,
            prev_first_label,
            prev_first_catalog,
            prev_last_label,
            prev_last_catalog,
            prev_is_empty,
            new_first_label,
            new_first_catalog,
            new_last_label,
            new_last_catalog,
            new_is_empty,
            source,
        ),
    )


async def check_idempotency(
    pool: AsyncConnectionPool,
    key: str,
) -> dict[str, Any] | None:
    """Check whether an idempotency key has been seen before.

    Returns the cached response_json dict if the key exists, else None.
    All SQL uses %s placeholders (T-03-24).

    Args:
        pool: Open psycopg AsyncConnectionPool.
        key:  The Idempotency-Key header value.

    Returns:
        The cached response_json as a dict, or None if not seen before.
    """
    sql = "SELECT response_json FROM gruvax.idempotency_keys WHERE key = %s"
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, (key,))
        row = await cur.fetchone()
    if row is None:
        return None
    cached: dict[str, Any] = row[0]
    return cached


async def store_idempotency(
    conn: Any,
    key: str,
    response: dict[str, Any],
) -> None:
    """Store an idempotency key with its response payload.

    Called inside the bulk-write transaction so the key is committed
    atomically with the boundary writes (Pitfall 7).
    All SQL uses %s placeholders (T-03-24).

    Args:
        conn:     Open psycopg async connection (inside a transaction).
        key:      The Idempotency-Key header value.
        response: The JSON-serializable response body to cache.
    """
    sql = """
INSERT INTO gruvax.idempotency_keys (key, response_json)
VALUES (%s, %s)
ON CONFLICT (key) DO NOTHING
"""
    import json

    await conn.execute(sql, (key, json.dumps(response)))


async def cleanup_idempotency(conn: Any) -> None:
    """Delete idempotency_keys rows older than 24 hours (Pitfall E).

    Called inside the bulk-write transaction so cleanup is bundled with
    each bulk commit — no separate cron job needed.
    All SQL uses %s placeholders (T-03-24).

    Args:
        conn: Open psycopg async connection (inside a transaction).
    """
    sql = """
DELETE FROM gruvax.idempotency_keys
WHERE created_at < now() - INTERVAL '24 hours'
"""
    await conn.execute(sql)


async def list_change_sets(
    pool: AsyncConnectionPool,
) -> list[dict[str, Any]]:
    """Return change-sets from boundary_history grouped by change_set_id.

    Returns newest-first ordered by the MAX changed_at per change-set.
    Includes source, cube_count, and the representative changed_at timestamp.
    All SQL uses %s placeholders (T-03-24).

    Args:
        pool: Open psycopg AsyncConnectionPool.

    Returns:
        List of dicts with keys change_set_id, source, changed_at, cube_count.
    """
    sql = """
SELECT
    change_set_id::text AS change_set_id,
    source,
    MAX(changed_at) AS changed_at,
    COUNT(*) AS cube_count
FROM gruvax.boundary_history
GROUP BY change_set_id, source
ORDER BY MAX(changed_at) DESC
LIMIT 100
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql)
        rows_raw = await cur.fetchall()
        cols_meta = [desc[0] for desc in (cur.description or [])]
    result: list[dict[str, Any]] = []
    for r in rows_raw:
        row_dict = dict(zip(cols_meta, r, strict=True))
        # Serialize datetime to ISO string for JSON
        if hasattr(row_dict.get("changed_at"), "isoformat"):
            row_dict["changed_at"] = row_dict["changed_at"].isoformat()
        result.append(row_dict)
    return result


async def fetch_change_set_rows(
    pool: AsyncConnectionPool,
    change_set_id: str,
) -> list[dict[str, Any]]:
    """Return all boundary_history rows for a given change_set_id.

    Used by the revert handler to know which cubes to restore.
    All SQL uses %s placeholders (T-03-24).

    Args:
        pool:          Open psycopg AsyncConnectionPool.
        change_set_id: UUID of the change-set to fetch.

    Returns:
        List of dicts with full history row fields.
    """
    sql = """
SELECT
    id, change_set_id::text AS change_set_id,
    unit_id, row, col,
    prev_first_label, prev_first_catalog, prev_last_label, prev_last_catalog, prev_is_empty,
    new_first_label, new_first_catalog, new_last_label, new_last_catalog, new_is_empty,
    changed_by, changed_at, source
FROM gruvax.boundary_history
WHERE change_set_id = %s::uuid
ORDER BY id
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, (change_set_id,))
        rows_raw = await cur.fetchall()
        cols_meta = [desc[0] for desc in (cur.description or [])]
    result: list[dict[str, Any]] = []
    for r in rows_raw:
        row_dict = dict(zip(cols_meta, r, strict=True))
        if hasattr(row_dict.get("changed_at"), "isoformat"):
            row_dict["changed_at"] = row_dict["changed_at"].isoformat()
        result.append(row_dict)
    return result


async def has_newer_changes(
    conn: Any,
    unit_id: int,
    row: int,
    col: int,
    original_changed_at: Any,
) -> bool:
    """Return True if a newer boundary_history row exists for this cube.

    Used by the revert handler to detect conflicts (D-12, Pitfall D).
    A conflict means a newer change-set has modified this cube since the
    change-set being reverted was written — reverting it would silently
    clobber the newer edit.

    All SQL uses %s placeholders (T-03-24).

    Args:
        conn:               Open psycopg async connection (inside a transaction).
        unit_id:            Cube unit ID.
        row:                Cube row index.
        col:                Cube column index.
        original_changed_at: The changed_at timestamp of the history row being reverted.

    Returns:
        True if a newer boundary_history row exists for this (unit, row, col).
    """
    sql = """
SELECT 1 FROM gruvax.boundary_history
WHERE unit_id = %s AND row = %s AND col = %s
  AND changed_at > %s
LIMIT 1
"""
    async with conn.cursor() as cur:
        await cur.execute(sql, (unit_id, row, col, original_changed_at))
        row_raw = await cur.fetchone()
    return row_raw is not None


async def cube_exact_match(
    pool: AsyncConnectionPool,
    label: str,
    catalog: str,
) -> bool:
    """Return True if an exact (label, catalog_number) pair exists in v_collection.

    Case-insensitive label match (lower(label) = lower(%s)); exact catalog_number match.
    Used by the admin validate endpoint to detect phantom boundary values (D-07).

    Source is exclusively v_collection (Pitfall 5).
    All SQL uses %s placeholders (T-03-16).

    Args:
        pool:    Open psycopg ``AsyncConnectionPool``.
        label:   Label to check.
        catalog: Catalog number to check.

    Returns:
        True if a record with this (label, catalog) pair exists in v_collection.
    """
    sql = """
SELECT 1
FROM gruvax.v_collection
WHERE lower(label) = lower(%s)
  AND catalog_number = %s
LIMIT 1
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, (label, catalog))
        row = await cur.fetchone()
    return row is not None

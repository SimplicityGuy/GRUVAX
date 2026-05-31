"""Database queries for GRUVAX.

All SQL uses psycopg parameterized placeholders (%s) — never
f-string interpolation of user input (T-01-07 / T-01-sqli-rewire SQLi protection).

Plan 01-06: all read paths that targeted the v1 cross-schema view (dropped
by migration 0009) have been rewired to ``gruvax.profile_collection`` with a
``WHERE profile_id = %s::uuid`` binding. Every rewired function accepts a
``profile_id`` parameter (defaulted to ``DEFAULT_PROFILE_UUID`` for P1
single-profile compatibility); P2 only needs to flip the call sites to pass the
session-bound profile_id (D-11).

Response-shape compatibility: ``profile_collection`` simplified the v1 column
set per D-04 (no ``collection_item_id``, no ``format``; ``primary_artist`` →
``artist``). The search/locate API response retains the historical key names
via SQL aliases (``artist AS primary_artist``, ``NULL::bigint AS
collection_item_id``, ``NULL::text AS format``) so the frontend +
contract-shape tests are unaffected by the data-source swap.

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

Phase 8 — OBS-07 counter + staleness + diagnostics functions:
  - ``get_sync_staleness_seconds``: seconds since last sync via profile_collection.synced_at.
  - ``increment_search_count``:     upsert search counters keyed by release_id only (D-04/D-05).
  - ``increment_selection_count``:  upsert selection counters keyed by release_id only (D-04/D-05).
  - ``get_top_searched``:           top-N records by all-time search_count (D-05/D-06).
  - ``get_phantom_boundary_count``: count non-empty boundaries not in profile_collection (OQ7).
  - ``reset_record_stats``:         TRUNCATE gruvax.record_stats (admin Reset stats action).
"""

from __future__ import annotations

import json
import re
import time
from typing import TYPE_CHECKING, Any

import psycopg.errors


if TYPE_CHECKING:
    from psycopg_pool import AsyncConnectionPool


# ── Default profile UUID (D-02 / D-11 — single-profile P1 fallback) ──────────
# Mirrors migration 0009 and the app.py lifespan constant.  P1's call sites pass
# this constant; P2 flips them to a per-request value bound from the session.
DEFAULT_PROFILE_UUID: str = "00000000-0000-0000-0000-000000000001"


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
    profile_id: str,
) -> str | None:
    """Return the top trigram-similarity match for *q* over label/artist terms.

    Runs only when FTS returned no results (D-11 — conservative).  Queries
    DISTINCT label and artist values from ``gruvax.profile_collection`` for the
    given profile via ``pg_trgm similarity()``.

    Graceful degradation (Pitfall E): if ``similarity()`` is undefined (pg_trgm
    not installed), catches ``psycopg.errors.UndefinedFunction`` and returns
    ``None`` so the caller still receives a 200 response.

    All user input goes through ``%s`` placeholders — never f-string
    interpolation (T-01-07, T-02-06, T-01-sqli-rewire).

    Args:
        pool:       Open psycopg ``AsyncConnectionPool``.
        q:          Raw user query string (already length-validated at router).
        profile_id: UUID of the profile to scope the suggestion to (required; D2-04).

    Returns:
        The best-matching term string if similarity > threshold, else ``None``.
    """
    sql = """
SELECT term, similarity(term, %s) AS sim
FROM (
    SELECT DISTINCT label AS term
    FROM gruvax.profile_collection
    WHERE profile_id = %s::uuid AND label IS NOT NULL
    UNION
    SELECT DISTINCT artist AS term
    FROM gruvax.profile_collection
    WHERE profile_id = %s::uuid AND artist IS NOT NULL
) AS terms
WHERE similarity(term, %s) > %s
ORDER BY sim DESC
LIMIT 1
"""
    try:
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(sql, (q, profile_id, profile_id, q, DID_YOU_MEAN_THRESHOLD))
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
    profile_id: str,
) -> tuple[list[SearchRow], float, str | None]:
    """Execute FTS + catalog-number union search over gruvax.profile_collection.

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

    Response-shape compatibility (Plan 01-06): the result dicts preserve the v1
    column names (``primary_artist``, ``collection_item_id``, ``format``) via
    SQL aliases (``artist AS primary_artist``, ``NULL::bigint AS
    collection_item_id``, ``NULL::text AS format``) so the frontend and the
    contract-shape integration tests do not need to change.  The underlying
    ``profile_collection`` schema dropped ``collection_item_id`` and ``format``
    per D-04; those fields are now always ``None`` in the API response.

    Args:
        pool:       Open psycopg ``AsyncConnectionPool``.
        q:          Raw user query string (already length-validated at router).
        limit:      Max rows to return (already range-validated at router).
        profile_id: UUID of the profile to search (required; D2-04).

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
    # All %s placeholders are fully parameterized (T-01-07, T-02-07,
    # T-01-sqli-rewire). profile_id binds via %s::uuid in every FROM clause.
    if is_catalog_query(q):
        sql = """
WITH fts AS (
    SELECT
        v.release_id,
        NULL::bigint AS collection_item_id,
        v.title,
        v.artist                  AS primary_artist,
        v.label,
        v.catalog_number,
        NULL::text   AS format,
        v.year,
        ts_rank_cd(
            setweight(to_tsvector('english', coalesce(v.catalog_number, '')), 'A')
            || setweight(v.fts_vector, 'C'),
            tsq.query,
            4
        ) AS score
    FROM gruvax.profile_collection v
    CROSS JOIN websearch_to_tsquery('english', %s) AS tsq(query)
    WHERE v.profile_id = %s::uuid
      AND (
        setweight(to_tsvector('english', coalesce(v.catalog_number, '')), 'A')
        || setweight(v.fts_vector, 'C')
      ) @@ tsq.query
    LIMIT 40
),
cat AS (
    SELECT
        release_id,
        NULL::bigint AS collection_item_id,
        title,
        artist        AS primary_artist,
        label,
        catalog_number,
        NULL::text    AS format,
        year,
        0.9::float AS score
    FROM gruvax.profile_collection
    WHERE profile_id = %s::uuid
      AND lower(regexp_replace(catalog_number, '[\\s\\-_./]+', '', 'g'))
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
        params: tuple[Any, ...] = (q, profile_id, profile_id, q, limit)
    else:
        # Standard FTS path (non-catalog query).
        # psycopg uses %s as the placeholder style (Python DB-API 2.0).
        # The query string itself uses %s; the params tuple provides the
        # values.  This is fully parameterized — q is never interpolated into
        # SQL (T-01-07, T-01-sqli-rewire).
        sql = """
WITH fts AS (
    -- websearch_to_tsquery is computed ONCE via the cross join (CR/WR-01),
    -- not twice (rank + WHERE). tsq.query is the single derived tsquery.
    SELECT
        v.release_id,
        NULL::bigint AS collection_item_id,
        v.title,
        v.artist                  AS primary_artist,
        v.label,
        v.catalog_number,
        NULL::text   AS format,
        v.year,
        ts_rank_cd(v.fts_vector, tsq.query, 4) AS score
    FROM gruvax.profile_collection v
    CROSS JOIN websearch_to_tsquery('english', %s) AS tsq(query)
    WHERE v.profile_id = %s::uuid
      AND v.fts_vector @@ tsq.query
    LIMIT 40
),
cat AS (
    SELECT
        release_id,
        NULL::bigint AS collection_item_id,
        title,
        artist        AS primary_artist,
        label,
        catalog_number,
        NULL::text    AS format,
        year,
        0.9::float AS score
    FROM gruvax.profile_collection
    WHERE profile_id = %s::uuid
      AND lower(regexp_replace(catalog_number, '[\\s\\-_./]+', '', 'g'))
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
        params = (q, profile_id, profile_id, q, limit)

    t0 = time.perf_counter()
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, params)
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
        did_you_mean = await did_you_mean_query(pool, q, profile_id)

    return rows, took_ms, did_you_mean


# ── Settings cache (Phase 3) ──────────────────────────────────────────────────


async def load_settings_cache(
    pool: AsyncConnectionPool,
    profile_id: str = DEFAULT_PROFILE_UUID,
) -> dict[str, Any]:
    """Load all rows from ``gruvax.settings`` into a key→value dict.

    Called once during FastAPI lifespan startup (step 3c) and stored in
    ``app.state.settings_cache``.  Provides nominal_capacity, idle TTL, and
    other Phase 3 runtime config without a per-request DB round-trip.

    Values are already JSONB-decoded by psycopg (numbers as int/float, strings
    as str, etc.).  Callers should use ``int(settings_cache.get("cube.nominal_capacity",
    95))`` to guard against a missing or malformed value.

    All SQL uses ``%s`` placeholders — no f-string interpolation (T-01-07).

    Note: settings have a nullable ``profile_id`` column added in migration 0009.
    In P1 all rows belong to the default profile; in P2 each profile gets its own
    settings rows.  This loader scopes to the given profile_id.

    Args:
        pool: Open psycopg ``AsyncConnectionPool``.
        profile_id: UUID string of the profile to scope the load to
            (P1: default UUID; P2: per-session profile_id from registry).

    Returns:
        Dict mapping ``key`` (str) → decoded JSONB ``value`` for every row in
        ``gruvax.settings`` for the given profile.  Returns ``{}`` if the table is empty.
    """
    sql = "SELECT key, value FROM gruvax.settings WHERE profile_id = %s::uuid"
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, (profile_id,))
        rows = await cur.fetchall()
    return {str(row[0]): row[1] for row in rows}


# ── Locate query ──────────────────────────────────────────────────────────────

LocateRecord = dict[str, Any]


async def get_release_for_locate(
    pool: AsyncConnectionPool,
    release_id: int,
    profile_id: str,
) -> LocateRecord | None:
    """Fetch label and catalog_number for a release_id from profile_collection.

    Used by ``GET /api/locate`` to retrieve the record metadata needed to
    call the cube-only estimator.

    Args:
        pool:       Open psycopg pool.
        release_id: The Discogs release ID to look up (integer, already
                    validated at the router).
        profile_id: UUID of the profile to scope the lookup to (required; D2-04).

    Returns:
        A dict with keys ``release_id``, ``label``, ``catalog_number``,
        or ``None`` if the release_id is not in the profile's collection.
    """
    sql = """
SELECT release_id, label, catalog_number
FROM gruvax.profile_collection v
WHERE v.profile_id = %s::uuid AND v.release_id = %s
LIMIT 1
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, (profile_id, release_id))
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
    profile_id: str = DEFAULT_PROFILE_UUID,
) -> list[dict[str, Any]]:
    """Return trigram near-misses for a phantom (label, catalog) pair.

    Queries ``gruvax.profile_collection`` for the top ``limit`` rows whose label
    and/or catalog_number has similarity above ``BOUNDARY_TRGM_THRESHOLD`` to
    the provided inputs.  Uses a combined similarity score (average of label and
    catalog similarities) for ranking.

    Graceful degradation (Pitfall E — mirrors ``did_you_mean_query``):
    if ``similarity()`` is undefined (pg_trgm not installed), catches
    ``psycopg.errors.UndefinedFunction`` and returns [] so the caller still
    receives a valid response.

    All user input goes through ``%s`` placeholders — never f-string
    interpolation (T-01-07, T-03-16, T-01-sqli-rewire).

    Args:
        pool:       Open psycopg ``AsyncConnectionPool``.
        label:      Label from the proposed boundary value.
        catalog:    Catalog number from the proposed boundary value.
        limit:      Maximum number of near-miss suggestions to return.
        profile_id: UUID of the profile to scope the search to (P1: default).

    Returns:
        List of dicts with keys ``label``, ``catalog_number``, ``similarity``.
        Empty list if pg_trgm is unavailable or no matches found.
    """
    sql = """
SELECT label, catalog_number,
       (similarity(lower(label), lower(%s)) * 0.5
        + similarity(lower(catalog_number), lower(%s)) * 0.5) AS sim
FROM gruvax.profile_collection
WHERE profile_id = %s::uuid
  AND (
      similarity(lower(label), lower(%s)) > %s
   OR similarity(lower(catalog_number), lower(%s)) > %s
  )
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
                    profile_id,
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


async def get_distinct_labels(
    pool: AsyncConnectionPool,
    profile_id: str = DEFAULT_PROFILE_UUID,
) -> list[str]:
    """Return all distinct labels present in gruvax.profile_collection, sorted.

    Used by the admin cubes editor autocomplete to populate the label picker
    (D-06).  Source is exclusively profile_collection for the active profile
    (Pitfall 5 — never reads raw discogsography tables).

    All SQL uses %s placeholders (T-03-16, T-01-sqli-rewire).

    Args:
        pool:       Open psycopg ``AsyncConnectionPool``.
        profile_id: UUID of the profile to scope the query to (P1: default).

    Returns:
        Sorted list of distinct label strings.
    """
    sql = """
SELECT DISTINCT label
FROM gruvax.profile_collection
WHERE profile_id = %s::uuid AND label IS NOT NULL
ORDER BY label
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, (profile_id,))
        rows = await cur.fetchall()
    return [str(row[0]) for row in rows]


async def get_catalogs_for_label(
    pool: AsyncConnectionPool,
    label: str,
    profile_id: str = DEFAULT_PROFILE_UUID,
) -> list[dict[str, Any]]:
    """Return all release_id + catalog_number for records with the given label.

    Used by the admin cubes editor autocomplete to populate the catalog# picker
    after a label has been selected (two-step dependent autocomplete, D-06).
    The label comparison is case-insensitive via lower().

    Source is exclusively profile_collection for the active profile (Pitfall 5).
    All SQL uses %s placeholders (T-03-16, T-01-sqli-rewire).

    Args:
        pool:       Open psycopg ``AsyncConnectionPool``.
        label:      Label to filter by (matched case-insensitively).
        profile_id: UUID of the profile to scope the query to (P1: default).

    Returns:
        List of dicts with keys ``release_id`` (int) and ``catalog_number`` (str),
        ordered by catalog_number.
    """
    sql = """
SELECT release_id, catalog_number
FROM gruvax.profile_collection
WHERE profile_id = %s::uuid AND lower(label) = lower(%s)
ORDER BY catalog_number
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, (profile_id, label))
        rows = await cur.fetchall()
    return [{"release_id": int(row[0]), "catalog_number": str(row[1])} for row in rows]


# ── Admin bulk-write + history + idempotency queries (Phase 3 Plan 05) ────────


async def fetch_current_boundary(
    conn: Any,
    unit_id: int,
    row: int,
    col: int,
    profile_id: str | None = None,
) -> dict[str, Any] | None:
    """Read the current boundary row for a cube using an existing connection.

    Used inside a transaction (atomic bulk write) to capture prev_* values
    before overwriting with new ones.  All SQL uses %s placeholders (T-03-24).

    Phase 5 (SEG-01): last_label / last_catalog have been dropped from
    cube_boundaries — they are no longer selected.  The returned dict will
    not contain those keys.  boundary_history still stores prev_last_* /
    new_last_* as nullable audit columns; callers pass None for new_last_*.

    Phase 6 (DATA-01): profile_id is required for all admin write/read paths.
    Passing None raises ValueError so callers on the admin path cannot silently
    scan all profiles (WR-03 — explicit contract, safe default).

    Args:
        conn:       Open psycopg async connection (inside a transaction).
        unit_id:    Cube unit ID.
        row:        Cube row index.
        col:        Cube column index.
        profile_id: UUID string of the profile to scope the read to (DATA-01).
                    Raises ValueError when None to prevent unscoped all-profile reads.

    Returns:
        Dict with boundary fields or None if the cube does not exist.
    """
    if profile_id is None:
        raise ValueError(
            "fetch_current_boundary: profile_id is required (WR-03). "
            "Pass the resolved profile_id from get_write_target."
        )
    sql = """
SELECT unit_id, row, col, first_label, first_catalog, is_empty
FROM gruvax.cube_boundaries
WHERE profile_id = %s::uuid AND unit_id = %s AND row = %s AND col = %s
"""
    params: tuple[Any, ...] = (profile_id, unit_id, row, col)
    async with conn.cursor() as cur:
        await cur.execute(sql, params)
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
    is_empty: bool,
    profile_id: str | None = None,
) -> int:
    """Update a cube's boundary values using an existing connection.

    Used inside a transaction — the caller is responsible for commit.
    All SQL uses %s placeholders (T-03-24, zero f-string interpolation).

    Phase 5 (SEG-01): last_label / last_catalog have been removed from
    cube_boundaries.  The UPDATE no longer touches those columns; they are
    now derived by SegmentCache from the next cube's cut point.

    Phase 6 (DATA-01): profile_id is required on all admin write paths.
    Passing None raises ValueError to prevent unscoped multi-profile writes
    (WR-03 — explicit contract, safe default).

    Args:
        conn:          Open psycopg async connection (inside a transaction).
        unit_id:       Cube unit ID.
        row:           Cube row index.
        col:           Cube column index.
        first_label:   New cut-point label (None only when is_empty=True).
        first_catalog: New cut-point catalog number (None only when is_empty=True).
        is_empty:      Whether the cube is empty.
        profile_id:    UUID string of the profile to scope the write to (DATA-01).
                       Raises ValueError when None to prevent unscoped writes.

    Returns:
        Number of rows affected (0 if the cube does not exist for this profile).
    """
    if profile_id is None:
        raise ValueError(
            "write_boundary: profile_id is required (WR-03). "
            "Pass the resolved profile_id from get_write_target."
        )
    sql = """
UPDATE gruvax.cube_boundaries
SET first_label = %s, first_catalog = %s,
    is_empty = %s
WHERE profile_id = %s::uuid AND unit_id = %s AND row = %s AND col = %s
"""
    params: tuple[Any, ...] = (first_label, first_catalog, is_empty, profile_id, unit_id, row, col)
    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        return cur.rowcount if cur.rowcount is not None else 0


async def write_history_row(
    conn: Any,
    change_set_id: str,
    unit_id: int,
    row: int,
    col: int,
    prev: dict[str, Any] | None,
    new_first_label: str | None,
    new_first_catalog: str | None,
    new_is_empty: bool,
    source: str,
    profile_id: str = DEFAULT_PROFILE_UUID,
) -> None:
    """Append one row to boundary_history for a single cube change.

    source must be 'manual', 'bulk', 'revert', or 'cut_insert' (DB CHECK
    constraint extended in migration 0005).  prev is None for cubes that had
    no prior boundary entry.  All SQL uses %s placeholders (T-03-24).

    Phase 5 (SEG-01): new_last_label / new_last_catalog have been removed from
    the signature.  The boundary_history table KEEPS these columns as nullable
    audit artifacts (A1 — no audit data is destroyed).  NULL is passed for
    new_last_* because cube_boundaries no longer stores last_* values.
    prev_last_* are also NULL for rows written after the 0005 migration.

    Phase 2 (D2 migration 0010): profile_id column is NOT NULL. Defaults to
    DEFAULT_PROFILE_UUID for P1 single-profile call sites.

    Args:
        conn:          Open psycopg async connection (inside a transaction).
        change_set_id: UUID shared across all cubes in one atomic commit.
        unit_id:       Cube unit ID.
        row:           Cube row index.
        col:           Cube column index.
        prev:          Dict with prev_* fields from fetch_current_boundary.
        new_first_label:   New cut-point label (None only when is_empty=True).
        new_first_catalog: New cut-point catalog number (None only when is_empty=True).
        new_is_empty:  Whether the cube is now empty.
        source:        'manual', 'bulk', 'revert', or 'cut_insert'.
        profile_id:    UUID of the profile these boundaries belong to (P1: default).
    """
    sql = """
INSERT INTO gruvax.boundary_history (
    profile_id, change_set_id, unit_id, row, col,
    prev_first_label, prev_first_catalog, prev_last_label, prev_last_catalog, prev_is_empty,
    new_first_label, new_first_catalog, new_last_label, new_last_catalog, new_is_empty,
    source
) VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""
    prev_first_label = prev.get("first_label") if prev else None
    prev_first_catalog = prev.get("first_catalog") if prev else None
    # prev_last_* are NULL for all rows written after migration 0005 (A1 audit artifact).
    prev_last_label: str | None = None
    prev_last_catalog: str | None = None
    prev_is_empty = bool(prev.get("is_empty", True)) if prev else True

    await conn.execute(
        sql,
        (
            profile_id,
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
            None,  # new_last_label — nullable audit artifact (A1, SEG-01)
            None,  # new_last_catalog — nullable audit artifact (A1, SEG-01)
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
    profile_id: str,
) -> list[dict[str, Any]]:
    """Return change-sets from boundary_history grouped by change_set_id.

    Returns newest-first ordered by the MAX changed_at per change-set.
    Scoped to the given profile_id (WR-02 — prevents cross-profile history leakage).
    Includes source, cube_count, and the representative changed_at timestamp.
    All SQL uses %s placeholders (T-03-24).

    Args:
        pool:       Open psycopg AsyncConnectionPool.
        profile_id: UUID of the profile to scope the query to (WR-02, DATA-01).

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
WHERE profile_id = %s::uuid
GROUP BY change_set_id, source
ORDER BY MAX(changed_at) DESC
LIMIT 100
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, (profile_id,))
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
    profile_id: str,
) -> list[dict[str, Any]]:
    """Return all boundary_history rows for a given change_set_id.

    Scoped to the given profile_id (WR-02 — prevents a revert from acting on
    a change-set belonging to a different profile at the same UUID).
    Used by the revert handler to know which cubes to restore.
    All SQL uses %s placeholders (T-03-24).

    Args:
        pool:          Open psycopg AsyncConnectionPool.
        change_set_id: UUID of the change-set to fetch.
        profile_id:    UUID of the profile to scope the query to (WR-02, DATA-01).

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
WHERE change_set_id = %s::uuid AND profile_id = %s::uuid
ORDER BY id
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, (change_set_id, profile_id))
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
    profile_id: str,
) -> bool:
    """Return True if a newer boundary_history row exists for this cube.

    Scoped to the given profile_id (WR-02 — prevents cross-profile conflict
    false-positives where a newer edit on a different profile triggers a skip).
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
        profile_id:         UUID of the profile to scope the conflict check to (WR-02).

    Returns:
        True if a newer boundary_history row exists for this (unit, row, col, profile).
    """
    sql = """
SELECT 1 FROM gruvax.boundary_history
WHERE unit_id = %s AND row = %s AND col = %s
  AND changed_at > %s
  AND profile_id = %s::uuid
LIMIT 1
"""
    async with conn.cursor() as cur:
        await cur.execute(sql, (unit_id, row, col, original_changed_at, profile_id))
        row_raw = await cur.fetchone()
    return row_raw is not None


async def cube_exact_match(
    pool: AsyncConnectionPool,
    label: str,
    catalog: str,
    profile_id: str = DEFAULT_PROFILE_UUID,
) -> bool:
    """Return True if an exact (label, catalog_number) pair exists in profile_collection.

    Case-insensitive label match (lower(label) = lower(%s)); exact catalog_number match.
    Used by the admin validate endpoint to detect phantom boundary values (D-07).

    Source is exclusively profile_collection for the active profile (Pitfall 5).
    All SQL uses %s placeholders (T-03-16, T-01-sqli-rewire).

    Args:
        pool:       Open psycopg ``AsyncConnectionPool``.
        label:      Label to check.
        catalog:    Catalog number to check.
        profile_id: UUID of the profile to scope the check to (P1: default).

    Returns:
        True if a record with this (label, catalog) pair exists for the profile.
    """
    sql = """
SELECT 1
FROM gruvax.profile_collection
WHERE profile_id = %s::uuid
  AND lower(label) = lower(%s)
  AND catalog_number = %s
LIMIT 1
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, (profile_id, label, catalog))
        row = await cur.fetchone()
    return row is not None


# ── Phase 8: OBS-07 — durable counters + diagnostics queries ─────────────────


async def get_sync_staleness_seconds(
    pool: AsyncConnectionPool,
    profile_id: str = DEFAULT_PROFILE_UUID,
) -> float | None:
    """Return seconds since the last sync for the profile, or None when empty.

    Plan 01-06: derives staleness from max(profile_collection.synced_at) for the
    given profile (the v1 v_collection.synced_at column was a passthrough of
    discogsography's collection_items.updated_at; under v2, each row's
    synced_at is set at the moment sync_profile() upserts it, which is the
    same semantic anchor — time since the profile last received fresh data).

    Note: app.py's lifespan background task supersedes this function for the
    OBS-06 metric in production; the function is retained for direct DB
    diagnostics + the unit test suite.

    All SQL uses %s placeholders (T-08-06, T-01-sqli-rewire).

    Args:
        pool:       Open psycopg ``AsyncConnectionPool``.
        profile_id: UUID of the profile to query (P1: default).

    Returns:
        Seconds as a non-negative float, or None when profile_collection has
        no rows for this profile (OBS-06).
    """
    sql = """
SELECT EXTRACT(EPOCH FROM (now() - max(synced_at)))
FROM gruvax.profile_collection
WHERE profile_id = %s::uuid
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, (profile_id,))
        row = await cur.fetchone()
    if row is None or row[0] is None:
        return None
    return float(row[0])


async def increment_search_count(
    pool: AsyncConnectionPool,
    release_id: int,
) -> None:
    """Upsert search counters for the given release_id (D-04, D-05, D-06).

    Counters are release_id-keyed aggregates; no query text is ever stored (OBS-07, T-08-05).
    Rolling 7-day bucket: search_count_7d resets to 1 when last_searched_at is older
    than 7 days; otherwise it increments (D-05).

    All SQL uses %s placeholders — never f-string interpolation (T-08-06).

    Args:
        pool:       Open psycopg ``AsyncConnectionPool``.
        release_id: Discogs release ID (integer, server-side — no user text stored).
    """
    # record_stats PK is (profile_id, release_id) after migration 0010.
    # Counters are tracked under the default profile (global stats for v1).
    sql = """
INSERT INTO gruvax.record_stats
    (profile_id, release_id, search_count, search_count_7d, last_searched_at, updated_at)
VALUES ('00000000-0000-0000-0000-000000000001'::uuid, %s, 1, 1, now(), now())
ON CONFLICT (profile_id, release_id) DO UPDATE SET
    search_count     = gruvax.record_stats.search_count + 1,
    search_count_7d  = CASE
        WHEN gruvax.record_stats.last_searched_at > now() - INTERVAL '7 days'
        THEN gruvax.record_stats.search_count_7d + 1
        ELSE 1
    END,
    last_searched_at = now(),
    updated_at       = now()
"""
    async with pool.connection() as conn:
        await conn.execute(sql, (release_id,))


async def increment_selection_count(
    pool: AsyncConnectionPool,
    release_id: int,
) -> None:
    """Upsert selection counters for the given release_id (D-04, D-05, D-06).

    Counters are release_id-keyed aggregates; no query text is ever stored (OBS-07, T-08-05).
    Rolling 7-day bucket: selection_count_7d resets to 1 when last_selected_at is older
    than 7 days; otherwise it increments (D-05).

    All SQL uses %s placeholders — never f-string interpolation (T-08-06).

    Args:
        pool:       Open psycopg ``AsyncConnectionPool``.
        release_id: Discogs release ID (integer, server-side — no user text stored).
    """
    # record_stats PK is (profile_id, release_id) after migration 0010.
    # Counters are tracked under the default profile (global stats for v1).
    sql = """
INSERT INTO gruvax.record_stats
    (profile_id, release_id, selection_count, selection_count_7d, last_selected_at, updated_at)
VALUES ('00000000-0000-0000-0000-000000000001'::uuid, %s, 1, 1, now(), now())
ON CONFLICT (profile_id, release_id) DO UPDATE SET
    selection_count     = gruvax.record_stats.selection_count + 1,
    selection_count_7d  = CASE
        WHEN gruvax.record_stats.last_selected_at > now() - INTERVAL '7 days'
        THEN gruvax.record_stats.selection_count_7d + 1
        ELSE 1
    END,
    last_selected_at = now(),
    updated_at       = now()
"""
    async with pool.connection() as conn:
        await conn.execute(sql, (release_id,))


async def get_top_searched(
    pool: AsyncConnectionPool,
    limit: int = 10,
    profile_id: str = DEFAULT_PROFILE_UUID,
) -> list[dict[str, Any]]:
    """Return top-N records by all-time search count, joined to profile_collection.

    Reads record_stats and gruvax.profile_collection exclusively — no direct
    discogsography table access (Pitfall 5).  Plan 01-06: rewired from
    v_collection.  The dict key ``primary_artist`` is preserved (alias over the
    new ``artist`` column) so frontend / contract tests are unchanged.

    DISTINCT ON (rs.release_id) ensures the JOIN to profile_collection (which
    can return multiple rows per release_id when the same release lives in
    multiple folders, since the PK is (profile_id, release_id, folder_id))
    yields exactly one row per release in the top-N result.

    All SQL uses %s placeholders (T-08-06, T-01-sqli-rewire).

    Args:
        pool:       Open psycopg ``AsyncConnectionPool``.
        limit:      Maximum number of rows to return (default 10).
        profile_id: UUID of the profile whose collection to join against (P1:
                    default).

    Returns:
        List of dicts with keys: release_id, title, primary_artist, search_count,
        search_count_7d, selection_count, selection_count_7d.
        Returns [] when record_stats is empty or no records match profile_collection.
    """
    sql = """
SELECT DISTINCT ON (rs.release_id)
    rs.release_id,
    v.title,
    v.artist AS primary_artist,
    rs.search_count,
    rs.search_count_7d,
    rs.selection_count,
    rs.selection_count_7d
FROM gruvax.record_stats rs
JOIN gruvax.profile_collection v
  ON v.release_id = rs.release_id AND v.profile_id = %s::uuid
ORDER BY rs.release_id, rs.search_count DESC
LIMIT %s
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, (profile_id, limit))
        rows_raw = await cur.fetchall()
        cols = [desc[0] for desc in (cur.description or [])]
    result = [dict(zip(cols, row, strict=True)) for row in rows_raw]
    # DISTINCT ON breaks the search_count ordering; re-sort in Python.
    result.sort(key=lambda r: r.get("search_count", 0) or 0, reverse=True)
    return result


async def get_phantom_boundary_count(
    pool: AsyncConnectionPool,
    profile_id: str = DEFAULT_PROFILE_UUID,
) -> int:
    """Count non-empty cube boundaries whose (first_label, first_catalog) is not in profile_collection.

    A "phantom" boundary references a (label, catalog) pair that no longer
    exists in the profile's collection (record may have been sold, deleted from
    Discogs, or the boundary was entered incorrectly).

    Reads gruvax.cube_boundaries and gruvax.profile_collection exclusively
    (Pitfall 5).  Plan 01-06: rewired from v_collection.
    All SQL uses %s placeholders (T-08-06, T-01-sqli-rewire).

    Args:
        pool:       Open psycopg ``AsyncConnectionPool``.
        profile_id: UUID of the profile whose collection to check against
                    (P1: default).

    Returns:
        Count of phantom boundaries (non-negative int). Returns 0 when
        cube_boundaries has no non-empty rows or all boundaries resolve in
        the profile's collection.
    """
    sql = """
SELECT COUNT(*)
FROM gruvax.cube_boundaries cb
WHERE cb.is_empty = FALSE
  AND cb.profile_id = %s::uuid
  AND NOT EXISTS (
      SELECT 1 FROM gruvax.profile_collection v
      WHERE v.profile_id = %s::uuid
        AND lower(v.label) = lower(cb.first_label)
        AND v.catalog_number = cb.first_catalog
  )
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, (profile_id, profile_id))
        row = await cur.fetchone()
    return int(row[0]) if row else 0


async def reset_record_stats(
    pool: AsyncConnectionPool,
) -> None:
    """TRUNCATE gruvax.record_stats — backs the PIN-gated Reset stats admin action (D-06).

    Clears all rows from the stats table. The caller (admin reset endpoint, Plan 04)
    is responsible for PIN/session gate enforcement before calling this function.

    All SQL uses %s placeholders (T-08-06); no parameters needed for TRUNCATE.

    Args:
        pool: Open psycopg ``AsyncConnectionPool``.
    """
    async with pool.connection() as conn:
        await conn.execute("TRUNCATE gruvax.record_stats")

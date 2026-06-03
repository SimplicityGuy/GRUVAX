"""Profile sync orchestration — staging-swap + advisory lock + cache refresh.

Public surface (Plan 01-03):
  - ``sync_profile(profile_id, app_state) -> dict`` — fetch the profile's
    discogsography collection, atomically replace the local
    ``gruvax.profile_collection`` cache, and refresh in-process caches
    (D-14). Returns ``{"status":"ok","item_count":N,"took_ms":T,"user_id":U}``.

Module-private helpers exported for tests:
  - ``_lock_key(profile_id)`` — sha256-based BIGINT for pg_advisory_lock.
  - ``_make_client(base_url, pat)`` — factory; tests monkeypatch this to
    inject an in-process fake.
  - ``_release_to_tuple(rel)`` — maps a contract envelope item to the COPY
    row tuple (D-04: id string → BIGINT).

Citations:
  - D-04 (release_id BIGINT)              — CONTEXT.md §decisions
  - D-05 (3-value last_sync_status)       — CONTEXT.md §decisions
  - D-06 (last_sync_error tag set)        — CONTEXT.md §decisions
  - D-11 (7-table fanout)                 — CONTEXT.md §decisions
  - D-14 (inline cache refresh)           — CONTEXT.md §decisions
  - Pitfall 1 (lock-not-released)         — RESEARCH.md
  - Pitfall 3 (transaction-state)         — RESEARCH.md
  - Pitfall 6 (pool-exhaustion)           — RESEARCH.md
  - Pitfall 7 (user_id COALESCE)          — RESEARCH.md
  - Pitfall 8 (sentinel-bytea PAT)        — RESEARCH.md

Security invariants:
  - All DML uses ``%s`` placeholders (T-01-07 / PATTERNS §SQL parameterization);
    the only constants interpolated as static literals are migration-style
    project constants (none in this module — every value comes via params).
  - The PAT plaintext is decrypted inside the function that constructs the
    ``DiscogsographyClient`` and goes out of scope as soon as the client owns
    the Authorization header.
  - The structlog log_redactor (gruvax.discogsography.log_redactor) defends
    any accidental Bearer ``dscg_*`` substring in log records.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import TYPE_CHECKING, Any

from cryptography.fernet import InvalidToken
import psycopg

from gruvax.discogsography.client import DiscogsographyClient
from gruvax.discogsography.errors import (
    NetworkError,
    PATRejected,
    RateLimitExhausted,
    ServerError,
    SyncInProgress,
)
from gruvax.settings import settings
from gruvax.sync.pat_crypto import decrypt_pat


if TYPE_CHECKING:
    from psycopg import AsyncConnection


__all__ = ["sync_profile"]

logger = logging.getLogger(__name__)


class _CacheRefreshFailed(Exception):
    """Internal sentinel: cache refresh raised AFTER the swap committed.

    Used to distinguish a post-commit refresh failure (DB state stays 'ok')
    from a sync-body failure (DB state goes to 'failed'). Caught by the
    outer ``sync_profile`` flow which unwraps and re-raises the original
    exception without writing a failed-status update.
    """

    def __init__(self, inner: BaseException) -> None:
        super().__init__(str(inner))
        self.inner = inner


# ── lock-key derivation (RESEARCH §Pattern 3) ────────────────────────────────


def _lock_key(profile_id: str) -> int:
    """Map a profile UUID string to a signed-int64 PG advisory-lock key.

    PG's advisory-lock key space is BIGINT (signed 64-bit). Take the first
    8 bytes of SHA-256("gruvax:profile_sync:<uuid>") and reinterpret as
    signed int64. Collision probability over <10 home-LAN profiles is
    effectively zero.
    """
    h = hashlib.sha256(f"gruvax:profile_sync:{profile_id}".encode()).digest()[:8]
    return int.from_bytes(h, byteorder="big", signed=True)


# ── connection-factory seam (Pitfall 6) ──────────────────────────────────────


def _conninfo() -> str:
    """Strip the SQLAlchemy ``+psycopg`` prefix to get a psycopg conninfo string."""
    return settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)


def _make_client(base_url: str, pat: str) -> DiscogsographyClient:
    """Factory hook tests monkeypatch to inject an in-process fake client.

    The default returns a vanilla DiscogsographyClient pointing at the
    configured base_url with the decrypted PAT. Tests replace this with a
    factory that swaps the inner httpx.AsyncClient for one bound to an
    ASGITransport(fake_app).
    """
    return DiscogsographyClient(base_url=base_url, pat=pat)


# ── release-row mapper (D-04) ────────────────────────────────────────────────


def _release_to_tuple(rel: dict[str, Any]) -> tuple[Any, ...]:
    """Map a discogsography contract item to the staging-table COPY tuple.

    Contract: ``id`` is a STRING; parse to BIGINT per D-04. No
    ``instance_id``. ``label`` and ``catalog_number`` are nullable.
    ``folder_id`` is integer (nullable in the wire format, but we default
    to 0 when absent so the composite PK never sees NULL — Postgres
    treats NULL PK columns as a UNIQUE-violation-skipping value, which
    would silently corrupt the swap).
    """
    folder_id = rel.get("folder_id")
    if folder_id is None:
        # Composite PK rejects NULL in folder_id; coerce to 0 sentinel.
        folder_id = 0
    return (
        int(rel["id"]),
        folder_id,
        rel.get("artist"),
        rel.get("title"),
        rel.get("label"),
        rel.get("catalog_number"),
        rel.get("year"),
    )


# ── short-lived status-update helper ─────────────────────────────────────────


_FAILED_STATUS_UPDATES: dict[type[Exception], str] = {
    PATRejected: "pat_rejected",
    RateLimitExhausted: "rate_limited",
    ServerError: "server_error",
    NetworkError: "network",
}


async def _record_failure(
    profile_id: str,
    *,
    error_tag: str | None,
    flip_revoked: bool,
) -> None:
    """Write a 'failed' status update on a fresh short-lived connection.

    The dedicated sync connection may be in an indeterminate state after
    a mid-sync exception. A separate connection guarantees the UPDATE
    commits regardless of the sync connection's transaction status.
    """
    conn = await psycopg.AsyncConnection.connect(_conninfo())
    try:
        if flip_revoked:
            await conn.execute(
                "UPDATE gruvax.profiles SET "
                "    last_sync_status = 'failed', "
                "    last_sync_error = %s, "
                "    app_token_revoked = TRUE "
                "WHERE id = %s::uuid",
                (error_tag, profile_id),
            )
        else:
            await conn.execute(
                "UPDATE gruvax.profiles SET "
                "    last_sync_status = 'failed', "
                "    last_sync_error = %s "
                "WHERE id = %s::uuid",
                (error_tag, profile_id),
            )
        await conn.commit()
    finally:
        await conn.close()


# ── stale-lock detection (Pitfall 1) ─────────────────────────────────────────


async def _detect_stale_in_progress(profile_id: str) -> tuple[bool, Any]:
    """Return (is_stale, last_sync_at) for the profile.

    A profile is "stale" when ``last_sync_status='in_progress'`` AND
    ``last_sync_at IS NULL OR last_sync_at < now() - INTERVAL '5 minutes'``.
    Used by ``sync_profile`` to produce an operator-actionable error
    message instead of an opaque SyncInProgress.
    """
    conn = await psycopg.AsyncConnection.connect(_conninfo())
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT last_sync_status, last_sync_at, "
                "       (last_sync_at IS NULL OR last_sync_at < now() - INTERVAL '5 minutes') "
                "FROM gruvax.profiles WHERE id = %s::uuid",
                (profile_id,),
            )
            row = await cur.fetchone()
        if not row:
            return (False, None)
        status, ts, is_stale_window = row
        return (status == "in_progress" and bool(is_stale_window), ts)
    finally:
        await conn.close()


# ── ingest loop (RESEARCH §Pattern 2 — staging-COPY) ─────────────────────────


_STAGING_DDL = """
CREATE TEMP TABLE profile_collection_staging (
    release_id     BIGINT NOT NULL,
    folder_id      INT,
    artist         TEXT,
    title          TEXT,
    label          TEXT,
    catalog_number TEXT,
    year           INT
) ON COMMIT DROP
"""

_STAGING_COPY = (
    "COPY profile_collection_staging "
    "(release_id, folder_id, artist, title, label, catalog_number, year) "
    "FROM STDIN"
)


async def _ingest_into_staging(
    conn: AsyncConnection[Any],
    client: Any,
) -> tuple[str, int]:
    """Stream every page into TEMP profile_collection_staging via COPY.

    Returns (user_id, row_count). The TEMP table is created inside the
    swap transaction (next step) — ON COMMIT DROP guarantees cleanup
    regardless of how the function exits.
    """
    # Get the first page first so we can capture user_id and decide
    # whether to keep paging.
    first_page = await client.first_page()
    user_id = str(first_page["user_id"])

    row_count = 0
    async with conn.cursor() as cur, cur.copy(_STAGING_COPY) as copy:
        for release in first_page.get("releases", []):
            await copy.write_row(_release_to_tuple(release))
            row_count += 1

        offset = first_page.get("limit", 200)
        has_more = bool(first_page.get("has_more"))
        while has_more:
            page = await client._get_page(limit=200, offset=offset)
            for release in page.get("releases", []):
                await copy.write_row(_release_to_tuple(release))
                row_count += 1
            has_more = bool(page.get("has_more"))
            offset += page.get("limit", 200)

    return user_id, row_count


# ── atomic swap (Pitfall 3 — single TX wrapping DELETE+INSERT+UPDATE) ────────


async def _swap_inside_tx(
    conn: AsyncConnection[Any],
    profile_id: str,
    row_count: int,
    user_id: str,
) -> tuple[int, bool]:
    """DELETE old rows, INSERT staging rows, UPDATE profiles — caller owns TX.

    Must be called from inside an ``async with conn.transaction()`` block.
    The caller's outer transaction guarantees that the staging TEMP table
    (created earlier in the same TX) is still in scope when the SELECT FROM
    runs here.

    Returns:
        (new_record_count, is_initial_import) computed atomically inside the TX.
        new_record_count: number of genuinely new releases this sync (>= 0, D-06).
        is_initial_import: True iff this is the first-ever sync (D-07).
    """
    # Pitfall 4: capture is_initial_import BEFORE the UPDATE that sets last_sync_at.
    # READ last_sync_at IS NULL here — after the UPDATE it will always be non-NULL.
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT last_sync_at IS NULL AS is_initial FROM gruvax.profiles WHERE id = %s::uuid",
            (profile_id,),
        )
        initial_row = await cur.fetchone()
    is_initial_import: bool = bool(initial_row[0]) if initial_row else True

    # Compute existing_count BEFORE the DELETE (Pitfall 9 — retry-safe scalar comparison).
    # Counts profile_collection rows that match staging on (release_id, folder_id IS NOT DISTINCT).
    # new_record_count = max(0, row_count - existing_count) — arrivals only, never negative (D-06).
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT COUNT(*) FROM gruvax.profile_collection pc"
            " JOIN profile_collection_staging s"
            "   ON pc.release_id = s.release_id"
            "  AND pc.folder_id IS NOT DISTINCT FROM s.folder_id"
            " WHERE pc.profile_id = %s::uuid",
            (profile_id,),
        )
        existing_row = await cur.fetchone()
    existing_count: int = int(existing_row[0]) if existing_row else 0
    new_record_count: int = max(0, row_count - existing_count)

    await conn.execute(
        "DELETE FROM gruvax.profile_collection WHERE profile_id = %s::uuid",
        (profile_id,),
    )
    # Extended INSERT: sets first_seen_at = NOW() for all rows in this sync (API-04).
    # Nullable column — rows from before migration 0012 retain NULL (Pitfall 3 compliant).
    await conn.execute(
        "INSERT INTO gruvax.profile_collection "
        "(profile_id, release_id, folder_id, artist, title, label, catalog_number, year,"
        " first_seen_at) "
        "SELECT %s::uuid, release_id, folder_id, artist, title, label, catalog_number, year,"
        "       NOW() "
        "FROM profile_collection_staging",
        (profile_id,),
    )
    # Extended UPDATE: stores diff state atomically with the swap (D-08, T-07-02).
    await conn.execute(
        "UPDATE gruvax.profiles SET "
        "    last_sync_at = NOW(), "
        "    last_sync_status = 'ok', "
        "    last_sync_item_count = %s, "
        "    last_sync_error = NULL, "
        "    discogsography_user_id = COALESCE(discogsography_user_id, %s::uuid), "
        "    app_token_revoked = FALSE, "
        "    last_new_record_count = %s, "
        "    last_sync_is_initial = %s "
        "WHERE id = %s::uuid",
        (row_count, user_id, new_record_count, is_initial_import, profile_id),
    )
    return new_record_count, is_initial_import


# ── cache refresh (D-14, Plan 02-02 — per-profile registry refresh) ──────────


async def _refresh_profile_caches(
    profile_id: str,
    app_state: Any,
    *,
    new_record_count: int = 0,
    is_initial_import: bool = False,
) -> None:
    """Reload the registry caches for one profile and publish collection_changed.

    Called from ``sync_profile`` AFTER the swap transaction commits (D-14).
    Order MUST be: invalidate → load cache → load snapshot → derive segment →
    publish (Pitfall A: never publish before all caches are fresh).

    Pool checkout here is brief — these are cache-rebuild reads, not the
    multi-second collection sync. Pool isolation (Pitfall 6) is preserved
    because the long-running sync used its own dedicated connection above.

    Args:
        profile_id: str UUID of the profile whose registry entries to reload.
        app_state: object with ``db_pool``, ``boundary_cache_registry``,
                   ``snapshot_registry``, ``segment_cache_registry``,
                   ``event_bus_registry`` attributes (typically
                   ``request.app.state``).
        new_record_count: number of new releases in this sync (>= 0, D-06).
        is_initial_import: True iff this is the first-ever sync for this profile (D-07).
    """
    pool = app_state.db_pool

    # Reload BoundaryCache for this profile (invalidate first — SEG-04 seam).
    cache = app_state.boundary_cache_registry[profile_id]
    cache.invalidate()
    await cache.load(pool, profile_id=profile_id)

    # Reload CollectionSnapshot for this profile.
    snapshot = app_state.snapshot_registry[profile_id]
    await snapshot.load(pool, profile_id=profile_id)

    # Re-derive SegmentCache (CPU-only, no DB call).
    seg = app_state.segment_cache_registry[profile_id]
    seg.derive(cache, snapshot, cache.overrides)

    # Publish collection_changed AFTER all caches are fresh (Pitfall A ordering).
    # Extended payload (API-04): includes new_record_count + is_initial_import.
    bus = app_state.event_bus_registry[profile_id]
    await bus.publish(
        "collection_changed",
        {
            "profile_id": profile_id,
            "new_record_count": new_record_count,
            "is_initial_import": is_initial_import,
        },
    )


# ── PAT load + sentinel detection (Pitfall 8) ────────────────────────────────


# Sentinel ciphertext set by migration 0009 — empty BYTEA + revoked=TRUE.
_SENTINEL_CIPHERTEXT = b""


async def _load_pat(profile_id: str) -> str:
    """Decrypt and return the PAT for ``profile_id``.

    Raises PATRejected if the row is in the post-migration sentinel state
    (empty ciphertext + revoked=TRUE) — short-circuit before any HTTP call.
    Raises PATRejected if Fernet decryption fails (key rotation orphan).
    """
    conn = await psycopg.AsyncConnection.connect(_conninfo())
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT app_token_encrypted, app_token_revoked "
                "FROM gruvax.profiles WHERE id = %s::uuid AND deleted_at IS NULL",
                (profile_id,),
            )
            row = await cur.fetchone()
        if row is None:
            raise PATRejected(f"profile not found: {profile_id}")
        ciphertext, revoked = bytes(row[0]) if row[0] is not None else b"", bool(row[1])
    finally:
        await conn.close()

    # Pitfall 8 — the migration seeded the row with `'\x'::bytea` (empty
    # bytes) + revoked=TRUE. Treat this as "PAT not set" and short-circuit
    # WITHOUT touching the discogsography API (no noisy 401 in their logs).
    if revoked and len(ciphertext) <= 1:
        raise PATRejected(
            "PAT not set for this profile — run `gruvax-set-pat --profile <name>` first"
        )

    try:
        return decrypt_pat(ciphertext)
    except InvalidToken as e:
        raise PATRejected(
            "PAT decryption failed — GRUVAX_SECRET_KEY may have rotated. "
            "Re-run `gruvax-set-pat` to re-encrypt."
        ) from e


# ── public surface ───────────────────────────────────────────────────────────


async def sync_profile(profile_id: str, app_state: Any) -> dict[str, Any]:
    """Stream-fetch the profile's discogsography collection and atomically
    swap the local cache. Refresh in-process caches inline (D-14).

    Args:
      profile_id: UUID string of the profile to sync.
      app_state: object with ``.db_pool``, ``.collection_snapshot``,
                 ``.boundary_cache``, ``.segment_cache`` attributes (typically
                 ``request.app.state``).

    Returns:
      ``{"status": "ok", "item_count": int, "took_ms": float, "user_id": str}``

    Raises:
      - SyncInProgress  — pg_try_advisory_lock returned FALSE
                          (with an operator-actionable message when the
                          existing state is a stale in_progress lock).
      - PATRejected     — 401/403 or decrypt failure; sets
                          app_token_revoked=TRUE + last_sync_error='pat_rejected'.
      - RateLimitExhausted — sets last_sync_error='rate_limited'.
      - ServerError     — sets last_sync_error='server_error'.
      - NetworkError    — sets last_sync_error='network'.
      - Any other Exception — sets last_sync_status='failed' (no tag) and re-raises.
    """
    t0 = time.perf_counter()
    lock_key = _lock_key(profile_id)

    # Pre-flight: load + decrypt the PAT BEFORE we acquire the lock. This
    # ensures sentinel-bytea Pitfall 8 short-circuits without acquiring
    # state that would need cleanup. PATRejected here is recorded with
    # flip_revoked=True.
    try:
        pat = await _load_pat(profile_id)
    except PATRejected:
        await _record_failure(profile_id, error_tag="pat_rejected", flip_revoked=True)
        raise

    # Acquire a dedicated connection (Pitfall 6) so the multi-second sync
    # never holds a pool slot. The pool is reserved for short-lived hot-path
    # work (e.g. parallel admin requests).
    conn = await psycopg.AsyncConnection.connect(_conninfo())
    # The dedicated connection bypasses the pool's configure() callback, so
    # the runtime search_path (D-12: "gruvax, public") is not yet set. The
    # COPY targets an unqualified TEMP table (resolves via pg_temp), but
    # the swap's DELETE/INSERT/UPDATE schema-qualify gruvax.* explicitly so
    # search_path is not strictly needed — set it anyway for parity with
    # pool-checked-out connections.
    await conn.execute("SELECT pg_catalog.set_config('search_path', 'gruvax, public', false)")
    try:
        # Session-scoped advisory lock — held across the staging-load and
        # the swap transaction (xact_lock auto-releases on COMMIT).
        async with conn.cursor() as cur:
            await cur.execute("SELECT pg_try_advisory_lock(%s)", (lock_key,))
            row = await cur.fetchone()
            if row is None:
                raise RuntimeError(
                    "pg_try_advisory_lock returned no row (psycopg invariant violation)"
                )
            acquired = bool(row[0])

        if not acquired:
            # Pitfall 1 — if the lock isn't held because a stale in_progress
            # state exists, surface an operator-actionable error.
            is_stale, ts = await _detect_stale_in_progress(profile_id)
            if is_stale:
                raise SyncInProgress(
                    f"Stale 'in_progress' state detected for profile {profile_id} "
                    f"(last_sync_at={ts}). Restart the API to clear the advisory lock."
                )
            raise SyncInProgress("Another sync for this profile is already running")

        client: Any = None
        try:
            # Set 'in_progress' early so the stale-lock heuristic above can
            # detect a hung sync after a crash.
            await conn.execute(
                "UPDATE gruvax.profiles SET "
                "    last_sync_status = 'in_progress', "
                "    last_sync_error = NULL "
                "WHERE id = %s::uuid",
                (profile_id,),
            )
            await conn.commit()

            client = _make_client(settings.DISCOGSOGRAPHY_BASE_URL, pat)

            # The CREATE TEMP TABLE + COPY + DELETE + INSERT SELECT + UPDATE
            # all run inside ONE explicit transaction. This guarantees:
            #   - The TEMP TABLE persists across the COPY → swap boundary
            #     (ON COMMIT DROP would otherwise nuke it between TXes).
            #   - The swap is atomic — no observer ever sees the cache in a
            #     mixed-row state (Pitfall 3 mitigation: no implicit-TX race
            #     where COPY commits before the DELETE).
            #   - On any exception inside the block, psycopg auto-rollbacks
            #     the entire critical section, leaving the live cache intact.
            async with conn.transaction():
                await conn.execute(_STAGING_DDL)
                user_id, row_count = await _ingest_into_staging(conn, client)
                new_record_count, is_initial_import = await _swap_inside_tx(
                    conn, profile_id, row_count, user_id
                )

            # Inline cache refresh (D-14). If this fails, the swap is still
            # durable AND last_sync_status is already 'ok' inside the committed
            # swap TX. We wrap the refresh exception in _CacheRefreshFailed
            # so the outer except-chain knows NOT to overwrite status='ok'
            # with 'failed'. The caller (Plan 04 admin endpoint) sees the
            # original exception via .inner and translates to a 500.
            # P2: use per-profile refresh (publishes collection_changed AFTER load).
            try:
                await _refresh_profile_caches(
                    profile_id,
                    app_state,
                    new_record_count=new_record_count,
                    is_initial_import=is_initial_import,
                )
            except Exception as exc:
                logger.exception(
                    "sync_profile: cache refresh failed AFTER commit "
                    "(profile=%s, item_count=%d) — DB state intact",
                    profile_id,
                    row_count,
                )
                raise _CacheRefreshFailed(exc) from exc

            took_ms = (time.perf_counter() - t0) * 1000.0
            return {
                "status": "ok",
                "item_count": row_count,
                "took_ms": took_ms,
                "user_id": user_id,
            }
        except _CacheRefreshFailed as wrapper:
            # Post-commit cache refresh failure: swap is durable, status='ok'.
            # Unwrap and re-raise the original exception so the caller sees
            # the underlying type (e.g. RuntimeError, ConnectionError).
            raise wrapper.inner from None
        except PATRejected:
            await _record_failure(profile_id, error_tag="pat_rejected", flip_revoked=True)
            raise
        except RateLimitExhausted:
            await _record_failure(profile_id, error_tag="rate_limited", flip_revoked=False)
            raise
        except ServerError:
            await _record_failure(profile_id, error_tag="server_error", flip_revoked=False)
            raise
        except NetworkError:
            await _record_failure(profile_id, error_tag="network", flip_revoked=False)
            raise
        except SyncInProgress:
            # Never set status='failed' on SyncInProgress — the OTHER sync owns
            # the row's last_sync_status. Just re-raise.
            raise
        except Exception:
            # Generic failure (e.g. mid-fetch non-typed crash): mark failed
            # with no error tag and re-raise.
            await _record_failure(profile_id, error_tag=None, flip_revoked=False)
            raise
        finally:
            if client is not None:
                try:
                    await client.aclose()
                except Exception:
                    logger.debug("sync_profile: client.aclose() failed (non-fatal)", exc_info=True)
    finally:
        # ALWAYS release the advisory lock and close the dedicated connection.
        try:
            async with conn.cursor() as cur:
                await cur.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))
        except Exception:
            logger.warning(
                "sync_profile: pg_advisory_unlock raised for profile=%s — connection close will release",
                profile_id,
                exc_info=True,
            )
        await conn.close()

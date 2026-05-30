"""Nightly sync scheduler + startup sweeps for GRUVAX.

This module owns:
  - next_fire_after() / now_local() — DST-safe wall-clock anchoring (D4-01)
  - _read_sync_cadence() — reads sync.cadence from gruvax.settings (D4-06)
  - _sync_loop() — long-running asyncio task (D4-01..D4-06)
  - _startup_catchup_sweep() — one-shot stale-profile sync on startup (D4-02)
  - _startup_purge_sweep() — one-shot orphaned-collection purge on startup (D4-11)
  - _purge_profile_collection() — DELETE profile_collection for a single profile (D4-13)

Design decision: catch-up and purge are TWO separate one-shot startup sweeps rather
than one combined pass. This makes each sweep independently testable, visible as
distinct startup phases in logs, and keeps them from masking each other's failures.
The lifespan calls:
  1. await _startup_catchup_sweep(pool, app_state, cadence)  — stale-profile sync
  2. await _startup_purge_sweep(pool)                         — orphan collection rows
  3. asyncio.create_task(_sync_loop(pool, app_state))        — CR-01 strong-ref loop

Security invariants:
  - All DML uses ``%s``/``%s::uuid`` placeholders — no f-string SQL (bandit B608).
  - PATs are NEVER passed to logger calls; only profile_id (UUID) and status strings.
  - Existing dscg_* structlog redactor covers any Bearer tokens that leak through
    underlying sync_profile() log calls.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any

from gruvax.sync.profile_sync import sync_profile


logger = logging.getLogger(__name__)

# Global settings live under the default profile UUID.
# Mirrors gruvax.db.queries.DEFAULT_PROFILE_UUID.
_DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"

# Fire-hour schedule per cadence (D4-03).
_CADENCE_FIRE_HOURS: dict[str, list[int]] = {
    "24h": [3],
    "12h": [3, 15],
    "6h": [3, 9, 15, 21],
}


# ── DST-safe scheduling ───────────────────────────────────────────────────────


def now_local() -> datetime:
    """Server-local TZ-aware datetime (respects OS/container TZ env).

    Uses datetime.now().astimezone() which returns the OS local timezone
    including any DST offset in effect at call time.
    """
    return datetime.now().astimezone()


def next_fire_after(now_aware: datetime, hour: int = 3) -> datetime:
    """DST-correct next occurrence of server-local ``hour``:00:00.

    Always returns a time strictly after ``now_aware``.  Uses ``fold=1`` to
    resolve any wall-clock ambiguity introduced by DST fall-back transitions
    (selects the post-transition offset).

    Invariants verified across 40 daily firings through US/Eastern DST transitions:
      - result > now_aware  (always strictly future)
      - Successive 03:00 firings are 22-26 wall-clock hours apart (D4-01)

    Args:
        now_aware: A TZ-aware datetime (e.g. from now_local()).
        hour: The target wall-clock hour (0-23).  Default 3 (03:00 local).

    Returns:
        The next occurrence of ``hour``:00:00 in the server's local TZ,
        strictly after ``now_aware``.
    """
    tz = now_aware.tzinfo
    today = now_aware.date()
    candidate_naive = datetime(today.year, today.month, today.day, hour, 0, 0)
    candidate = candidate_naive.replace(tzinfo=tz, fold=1)
    if candidate <= now_aware:
        tomorrow = today + timedelta(days=1)
        candidate_naive = datetime(
            tomorrow.year, tomorrow.month, tomorrow.day, hour, 0, 0
        )
        candidate = candidate_naive.replace(tzinfo=tz, fold=1)
    return candidate


# ── Settings read ─────────────────────────────────────────────────────────────


async def _read_sync_cadence(pool: Any) -> str:
    """Read sync.cadence from gruvax.settings under the default profile UUID.

    Returns "24h" if the row is absent (Pitfall 6 / D4-06 fallback default).
    Stored value is a JSON string e.g. '\"24h\"'; strips quotes if present.

    Uses fetchall() + first-row access for compatibility with test stubs
    that implement fetchall() but not fetchone().
    """
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT value FROM gruvax.settings "
            "WHERE profile_id = %s::uuid AND key = 'sync.cadence'",
            (_DEFAULT_PROFILE_UUID,),
        )
        rows = await cur.fetchall()
    if not rows:
        return "24h"
    val = rows[0][0]
    if isinstance(val, str):
        return val.strip('"')
    return str(val)


# ── Nightly sync loop ─────────────────────────────────────────────────────────


async def _sync_loop(pool: Any, app_state: Any) -> None:
    """Long-running asyncio task: nightly scheduled sync for all eligible profiles.

    Mirrors _refresh_all_profiles_state() in app.py — outer while-True with
    try/except Exception (NOT BaseException so CancelledError propagates cleanly
    on uvicorn SIGTERM, per Pitfall 1 in 04-RESEARCH).

    Loop structure (sleep → sync, scheduled-fire ordering):
      1. Read current cadence from settings (re-read each tick for live config).
      2. If "off": park for 60s and continue (no sync).
      3. Compute the next scheduled fire time and sleep until then.
      4. On wake (i.e. at the scheduled wall-clock time) fetch eligible profiles
         and sync each one.

    This sleep→sync ordering means the loop does NOT sync on startup — it only
    fires at the scheduled wall-clock time (03:00 etc., D4-01).  Staleness at boot
    is the responsibility of the separate _startup_catchup_sweep (D4-02), which
    runs before this task is registered.  Keeping the routine loop sleep-first
    avoids a full re-sync of every profile on each process restart (rate-limit
    safety) and prevents the loop from racing unrelated in-flight requests.

    Cadence (D4-03):
      24h → fires at 03:00
      12h → fires at 03:00 + 15:00
      6h  → fires at 03:00, 09:00, 15:00, 21:00
      off → parks (sleep 60s, recheck)

    Skip policy (D4-04): excludes app_token_revoked=TRUE and last_sync_status='in_progress'.
    Per-profile isolation: each sync_profile() call has its own try/except Exception;
    one failed profile never aborts the pass for subsequent profiles.
    """
    while True:
        try:
            cadence = await _read_sync_cadence(pool)

            if cadence == "off":
                # Park: recheck cadence in 60s without syncing anyone (D4-06).
                await asyncio.sleep(60)
                continue

            # Sleep-FIRST: compute the next scheduled fire time and sleep until it.
            # The loop must NOT sync on startup (D4-01) — boot-time staleness is
            # handled by _startup_catchup_sweep (D4-02). Compute next fire from the
            # cadence's hour list (D4-03).
            fire_hours = _CADENCE_FIRE_HOURS.get(cadence, [3])
            now = now_local()
            next_fire = min(next_fire_after(now, h) for h in fire_hours)
            sleep_secs = (next_fire - now).total_seconds()

            logger.info(
                "nightly_sync: cadence=%s next_fire=%s sleep_secs=%.0f",
                cadence,
                next_fire.isoformat(),
                sleep_secs,
            )
            await asyncio.sleep(max(sleep_secs, 1))

            # Woke at the scheduled time → run the sync pass for eligible profiles.
            # Re-fetch under the skip policy (D4-04): non-deleted, non-revoked,
            # non-in_progress. Parameterized SQL only — no f-strings (bandit B608).
            async with pool.connection() as conn, conn.cursor() as cur:
                await cur.execute(
                    "SELECT id::text FROM gruvax.profiles "
                    "WHERE deleted_at IS NULL "
                    "  AND app_token_revoked = FALSE "
                    "  AND (last_sync_status IS NULL OR last_sync_status != 'in_progress') "
                    "ORDER BY created_at"
                )
                profile_ids = [row[0] for row in await cur.fetchall()]

            for pid in profile_ids:
                try:
                    await sync_profile(pid, app_state)
                    logger.info("nightly_sync: profile=%s OK", pid)
                except Exception as exc:
                    # Per-profile isolation: log + continue (never abort the loop).
                    logger.warning("nightly_sync: profile=%s FAILED: %s", pid, exc)

        except asyncio.CancelledError:
            logger.info("nightly_sync: loop cancelled (shutdown)")
            raise  # Re-raise so FastAPI/uvicorn can tear down cleanly (Pitfall 1).
        except Exception as exc:
            logger.warning(
                "nightly_sync: outer loop error: %s — will retry in 60s", exc
            )
            await asyncio.sleep(60)


# ── Startup sweeps ────────────────────────────────────────────────────────────


async def _startup_catchup_sweep(
    pool: Any, app_state: Any, cadence: str
) -> None:
    """One-shot catch-up sweep: sync any non-revoked stale profiles on startup.

    D4-02: profiles whose last_sync_at is older than the cadence threshold are
    synced sequentially (order by created_at) before _sync_loop is registered.

    The sweep applies the same skip policy as _sync_loop (D4-04): excludes
    app_token_revoked=TRUE and last_sync_status='in_progress'. This prevents
    a sync-storm on restart when multiple profiles are simultaneously stale.

    When cadence is "off", no catch-up is performed.
    """
    if cadence == "off":
        logger.info("startup_catchup: cadence=off — skipping catch-up sweep")
        return

    cadence_hours = {"24h": 24, "12h": 12, "6h": 6}.get(cadence, 24)

    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id::text FROM gruvax.profiles "
            "WHERE deleted_at IS NULL "
            "  AND app_token_revoked = FALSE "
            "  AND (last_sync_status IS NULL OR last_sync_status != 'in_progress') "
            "  AND (last_sync_at IS NULL "
            "       OR last_sync_at < NOW() - (%s * INTERVAL '1 hour')) "
            "ORDER BY created_at",
            (cadence_hours,),
        )
        stale_ids = [row[0] for row in await cur.fetchall()]

    if not stale_ids:
        logger.info("startup_catchup: no stale profiles to sync")
        return

    logger.info(
        "startup_catchup: syncing %d stale profile(s): %s",
        len(stale_ids),
        stale_ids,
    )
    for pid in stale_ids:
        try:
            await sync_profile(pid, app_state)
            logger.info("startup_catchup: profile=%s OK", pid)
        except Exception as exc:
            logger.warning("startup_catchup: profile=%s FAILED: %s", pid, exc)


async def _startup_purge_sweep(pool: Any) -> None:
    """One-shot purge sweep: remove profile_collection rows for soft-deleted profiles.

    D4-11: backstops any delete-time purge that may have been skipped (e.g. app
    crash mid-delete, pre-Phase-4 deletes). Runs before _sync_loop is registered.

    D4-12 predicate: deleted_at IS NOT NULL AND profile_collection rows still exist.
    D4-13: removes ONLY profile_collection rows; profile row + audit lineage survive.
    D4-14: profile row is never hard-deleted.
    """
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT DISTINCT p.id::text "
            "FROM gruvax.profiles p "
            "JOIN gruvax.profile_collection pc ON pc.profile_id = p.id "
            "WHERE p.deleted_at IS NOT NULL",
        )
        orphaned_ids = [row[0] for row in await cur.fetchall()]

    if not orphaned_ids:
        logger.info("startup_purge: no orphaned profile_collection rows found")
        return

    logger.info(
        "startup_purge: purging profile_collection for %d soft-deleted profile(s): %s",
        len(orphaned_ids),
        orphaned_ids,
    )
    for pid in orphaned_ids:
        await _purge_profile_collection(pool, pid)


# ── Purge helper ──────────────────────────────────────────────────────────────


async def _purge_profile_collection(pool: Any, profile_id: str) -> None:
    """DELETE profile_collection rows for a soft-deleted profile.

    D4-13: removes ONLY gruvax.profile_collection rows for the given profile.
    Preserves: profile row, settings, cube_boundaries, segment_overrides,
    record_stats, boundary_history.

    FK-SAFETY: profile_collection.profile_id REFERENCES profiles(id) ON DELETE
    CASCADE — but profiles are NEVER hard-deleted (D4-14), so the cascade never
    fires. Nothing else REFERENCES profile_collection. Zero audit-cascade risk.

    Security: uses ``%s::uuid`` placeholder only — no f-string interpolation
    (bandit B608). profile_id is a server-derived UUID, never user-supplied at
    call sites.
    """
    async with pool.connection() as conn:
        await conn.execute(
            "DELETE FROM gruvax.profile_collection WHERE profile_id = %s::uuid",
            (profile_id,),
        )
        await conn.commit()
    logger.info("purge_profile_collection: removed rows for profile=%s", profile_id)

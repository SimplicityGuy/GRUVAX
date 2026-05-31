"""LED highlight lifecycle: cancelable revert registry + ambient baseline.

Phase 6 Plan 02: Highlight Lifecycle (LED-11, LED-12, LED-13)

This module owns the server-scheduled ambient-revert lifecycle:

  1. ``publish_ambient`` — write the retained idle/ambient state/* baseline for
     every cube (or a specific subset).  Ambient is the ONLY meaning of "ambient"
     here (D-20 / D-24); it is the idle LED state, NOT the label-span tier.

  2. ``HighlightRegistry`` — bounded, leak-free in-process registry of cancelable
     asyncio.Task handles.  Lives on ``app.state.highlight_registry``.
     Size is O(active highlights): default mode keeps at most 1; retain mode grows
     by one per search and shrinks as TTLs fire.  (T-06-18, T-06-19)

  3. ``schedule_revert`` — body of each revert task: sleeps the TTL (injectable
     via the ``sleep`` parameter for testability), then publishes ambient state/*
     for the specific cubes that were highlighted, then pops the registry entry.
     (D-22 testability seam)

  4. ``illuminate_with_lifecycle`` — lifecycle-aware illuminate entry point.
     Reads ``led_highlight.retain_mode`` from settings_cache.
     Default mode (retain_mode=false): cancels+reverts the prior highlight FIRST,
     then calls ``fan_out_illuminate``, then schedules the TTL revert.
     Retain mode (retain_mode=true): adds a new entry without cancelling prior;
     each highlight reverts independently after ``led_highlight.retain_ttl_seconds``.
     (D-22, D-23)

  5. ``cancel_and_revert_all`` — shutdown path: cancels every registered task
     and best-effort publishes ambient for its cubes; empties the registry.
     (T-06-22)

Degraded mode posture (D-01, D-22):
  Every function that takes a ``client`` argument short-circuits with a logged
  warning and returns immediately when ``client is None``.  A broker hiccup NEVER
  raises into the request path or the lifespan teardown.

Brightness-tier naming (D-24 — LOCKED):
  ``led_brightness.ambient`` — the idle/ambient tier.  Used here.
  ``led_brightness.span``    — the label-span tier.  Used by fan_out_illuminate, NOT here.
  These are distinct keys; never substitute one for the other.

Injectable clock (D-22 testability):
  ``schedule_revert`` and ``illuminate_with_lifecycle`` accept a ``sleep`` keyword
  argument (default: ``asyncio.sleep``) so tests can inject a near-zero or fake
  clock without real 180s/900s waits.

Logging (project convention):
  Use %-style format strings; never f-strings in log calls.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any
import uuid

from gruvax.mqtt.publishers import fan_out_illuminate, publish_ambient


if TYPE_CHECKING:
    import aiomqtt


logger = logging.getLogger(__name__)

# WR-02: hard cap on concurrently-retained highlights in retain mode.  Without a
# cap, retain mode is bounded only by the TTL — a fast typist can register
# hundreds of highlight tasks before any TTL fires, each holding an asyncio task
# and a cubes list (a memory/task-leak risk on the constrained Pi/lux host).
# When the cap is reached, the oldest retained highlight is cancelled + reverted
# before the new one is added, so the registry never exceeds this bound while
# preserving normal retain-mode UX.
_RETAIN_MODE_MAX_HIGHLIGHTS = 64


# ── HighlightRegistry ─────────────────────────────────────────────────────────


class _RegistryEntry:
    """Internal: one registered highlight."""

    __slots__ = ("cubes", "task")

    def __init__(self, task: asyncio.Task[None], cubes: list[dict[str, int]]) -> None:
        self.task = task
        self.cubes = cubes


class HighlightRegistry:
    """Bounded in-process registry mapping highlight_id → (task, cubes).

    Leak-free invariant: each ``schedule_revert`` task pops its own entry from
    the registry in a ``finally`` block.  ``cancel_and_revert_all`` empties the
    registry at shutdown.

    T-06-18: registry size stays O(active highlights) — never grows unbounded.
    """

    def __init__(self) -> None:
        self._entries: dict[str, _RegistryEntry] = {}

    def add(
        self,
        highlight_id: str,
        task: asyncio.Task[None],
        cubes: list[dict[str, int]],
    ) -> None:
        """Register a highlight with its revert task and affected cubes."""
        self._entries[highlight_id] = _RegistryEntry(task=task, cubes=cubes)

    def pop(self, highlight_id: str) -> _RegistryEntry | None:
        """Remove and return the entry for *highlight_id*, or None if absent (idempotent)."""
        return self._entries.pop(highlight_id, None)

    def items(self) -> list[tuple[str, _RegistryEntry]]:
        """Return a snapshot of (highlight_id, entry) pairs for safe iteration."""
        return list(self._entries.items())

    def values(self) -> list[_RegistryEntry]:
        """Return a snapshot of entries for safe iteration."""
        return list(self._entries.values())

    def __len__(self) -> int:
        return len(self._entries)


# ── schedule_revert ───────────────────────────────────────────────────────────


async def schedule_revert(
    registry: HighlightRegistry,
    client: aiomqtt.Client | None,
    settings_cache: dict[str, Any],
    *,
    highlight_id: str,
    cubes: list[dict[str, int]],
    delay_seconds: int | float,
    sleep: Any = asyncio.sleep,
) -> None:
    """Revert task body: sleep the TTL then republish ambient state/* for affected cubes.

    After the delay, publishes the retained ambient baseline for exactly *cubes* —
    not all cubes.  Pops the registry entry in a ``finally`` so the entry is always
    removed whether the task completes, is cancelled, or raises.

    D-22: ``sleep`` is the injectable clock seam.  Pass ``asyncio.sleep`` (the default)
    in production; pass a near-zero coroutine in tests so there is no real wait.

    Degraded mode: if ``client`` is None the ambient publish is skipped (logged warning);
    the registry entry is still removed.
    """
    try:
        await sleep(delay_seconds)
        if client is None:
            logger.warning(
                "MQTT not connected — revert for highlight_id=%s skipped (degraded mode)",
                highlight_id,
            )
            return
        # Re-publish ambient state/* for the specific affected cubes (no pool needed;
        # cubes are passed explicitly to avoid a DB round-trip during the revert).
        await publish_ambient(client, None, settings_cache, cubes=cubes)
        logger.info(
            "Revert complete for highlight_id=%s (%d cubes reverted to ambient)",
            highlight_id,
            len(cubes),
        )
    finally:
        registry.pop(highlight_id)


# ── illuminate_with_lifecycle ─────────────────────────────────────────────────


async def illuminate_with_lifecycle(
    registry: HighlightRegistry,
    client: aiomqtt.Client | None,
    settings_cache: dict[str, Any],
    body: Any,
    *,
    sleep: Any = asyncio.sleep,
) -> None:
    """Lifecycle-aware illuminate: manage the revert registry around fan_out_illuminate.

    Reads ``led_highlight.retain_mode`` from settings_cache:

    Default mode (retain_mode=false, D-22):
      1. Cancel every currently-registered highlight's revert task.
      2. Immediately revert the cancelled cubes to ambient (best-effort).
      3. Call fan_out_illuminate for the new selection.
      4. Schedule a TTL revert keyed ``led_highlight.active_ttl_seconds``.

    Retain mode (retain_mode=true, D-23):
      1. Call fan_out_illuminate for the new selection (no cancellation of prior).
      2. Schedule an independent TTL revert keyed ``led_highlight.retain_ttl_seconds``.

    T-06-19: In default mode at most one active highlight task exists (the new one).

    Degraded mode: if ``client`` is None, logs and returns without raising.

    Args:
        registry:       The highlight registry on app.state.
        client:         The aiomqtt client, or None in degraded mode.
        settings_cache: The gruvax.settings key/value dict (from app.state.settings_cache).
        body:           The IlluminateRequest / LocateResult body (duck-typed).
        sleep:          Injectable clock; default asyncio.sleep; tests pass a near-zero coroutine.
    """
    if client is None:
        logger.warning(
            "MQTT not connected — illuminate_with_lifecycle for release_id=%s skipped (degraded mode)",
            getattr(body, "release_id", "unknown"),
        )
        return

    # ── Resolve retain mode ───────────────────────────────────────────────────
    retain_mode_raw = settings_cache.get("led_highlight.retain_mode", "false")
    # Settings values are stored as JSON-encoded strings; "false"/"true" (no quotes).
    if isinstance(retain_mode_raw, str):
        retain_mode = retain_mode_raw.strip('"').lower() == "true"
    else:
        retain_mode = bool(retain_mode_raw)

    # ── Compute affected cubes (primary + span) ───────────────────────────────
    primary = body.primary_cube  # dict | None
    label_span = body.label_span or []  # list[dict]

    # Collect all distinct cubes this highlight touches.
    seen: set[tuple[int, int, int]] = set()
    affected: list[dict[str, int]] = []
    for cube_dict in ([primary] if primary is not None else []) + list(label_span):
        if cube_dict is None:
            continue
        key = (cube_dict["unit_id"], cube_dict["row"], cube_dict["col"])
        if key not in seen:
            seen.add(key)
            affected.append(
                {"unit_id": cube_dict["unit_id"], "row": cube_dict["row"], "col": cube_dict["col"]}
            )

    # ── Default mode: cancel prior + immediate ambient revert ─────────────────
    if not retain_mode:
        prior_entries = registry.items()
        for hid, entry in prior_entries:
            entry.task.cancel()
            registry.pop(hid)
            # Best-effort immediate ambient revert for the cancelled cubes.
            try:
                await publish_ambient(client, None, settings_cache, cubes=entry.cubes)
                logger.info(
                    "Cancelled prior highlight %s; reverted %d cubes to ambient",
                    hid,
                    len(entry.cubes),
                )
            except Exception as exc:
                logger.warning(
                    "Best-effort ambient revert for cancelled highlight %s failed: %s",
                    hid,
                    exc,
                )
    else:
        # ── Retain mode: enforce the hard cap by evicting oldest (WR-02) ──────
        # registry.items() preserves insertion order (dict ordering), so the
        # leading entries are the oldest.  Evict just enough of them to make room
        # for the new highlight, cancelling + reverting each before removal.
        while len(registry) >= _RETAIN_MODE_MAX_HIGHLIGHTS:
            oldest = registry.items()
            if not oldest:
                break
            hid, entry = oldest[0]
            entry.task.cancel()
            registry.pop(hid)
            try:
                await publish_ambient(client, None, settings_cache, cubes=entry.cubes)
                logger.warning(
                    "Retain-mode highlight cap (%d) reached; evicted oldest highlight %s "
                    "(reverted %d cubes to ambient) to bound registry growth (WR-02)",
                    _RETAIN_MODE_MAX_HIGHLIGHTS,
                    hid,
                    len(entry.cubes),
                )
            except Exception as exc:
                logger.warning(
                    "Best-effort ambient revert for evicted highlight %s failed: %s",
                    hid,
                    exc,
                )

    # ── Publish the new highlight ─────────────────────────────────────────────
    try:
        await fan_out_illuminate(client, body, settings_cache)
    except Exception as exc:
        logger.warning(
            "fan_out_illuminate failed for release_id=%s: %s",
            getattr(body, "release_id", "unknown"),
            exc,
        )

    # ── Schedule the revert task ──────────────────────────────────────────────
    if retain_mode:
        ttl_raw = settings_cache.get("led_highlight.retain_ttl_seconds", "900")
    else:
        ttl_raw = settings_cache.get("led_highlight.active_ttl_seconds", "180")

    try:
        delay_seconds = int(str(ttl_raw).strip('"'))
    except (ValueError, TypeError):
        delay_seconds = 900 if retain_mode else 180
        logger.warning(
            "Invalid TTL value %r; falling back to %d seconds",
            ttl_raw,
            delay_seconds,
        )

    highlight_id = str(uuid.uuid4())
    task = asyncio.create_task(
        schedule_revert(
            registry,
            client,
            settings_cache,
            highlight_id=highlight_id,
            cubes=affected,
            delay_seconds=delay_seconds,
            sleep=sleep,
        )
    )
    registry.add(highlight_id, task, affected)
    logger.info(
        "Highlight %s scheduled (retain_mode=%s, ttl=%ds, cubes=%d)",
        highlight_id,
        retain_mode,
        delay_seconds,
        len(affected),
    )


# ── cancel_and_revert_all ─────────────────────────────────────────────────────


async def cancel_and_revert_all(
    registry: HighlightRegistry,
    client: aiomqtt.Client | None,
    settings_cache: dict[str, Any],
) -> None:
    """Shutdown path: cancel all pending revert tasks and best-effort revert their cubes.

    Called in the lifespan teardown so no pending tasks survive the process.
    T-06-22: prevents leaked asyncio tasks after a graceful shutdown.

    Degrades gracefully: if client is None, task cancellations still happen but
    ambient publishes are skipped.
    """
    entries = registry.items()
    if not entries:
        return

    logger.info("cancel_and_revert_all: cancelling %d pending revert tasks", len(entries))

    for highlight_id, entry in entries:
        try:
            entry.task.cancel()
        except Exception as exc:
            logger.warning(
                "Failed to cancel revert task for highlight_id=%s: %s", highlight_id, exc
            )

        if client is not None:
            try:
                await publish_ambient(client, None, settings_cache, cubes=entry.cubes)
            except Exception as exc:
                logger.warning(
                    "Best-effort ambient revert on shutdown for highlight_id=%s failed: %s",
                    highlight_id,
                    exc,
                )

        registry.pop(highlight_id)

    logger.info("cancel_and_revert_all: registry cleared")

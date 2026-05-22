# Phase 4: Realtime Live Updates - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-21
**Phase:** 04-realtime-live-updates
**Areas discussed:** "Updating" indicator lifecycle, Stale-highlight behavior, Optimistic edit + rollback feel, Connectivity scope line

> Phase entered MVP mode and was SPIDR-split (Paths axis) before discussion: the realtime
> happy-path is this phase; Offline Resilience and Privacy + Recently-Pulled were carved out
> as deferred slices.

---

## "Updating" indicator lifecycle (RTM-04)

**When it appears**

| Option | Description | Selected |
|--------|-------------|----------|
| While owner is mid-edit | admin_editing heartbeat (debounced); kiosk shimmers before commit. Matches roadmap criterion 1. | ✓ |
| Only a brief pulse on commit | No pre-commit signal; cubes pulse when boundary_changed lands. | |
| Both | Pre-commit shimmer + confirming pulse on commit. | |

**How it looks**

| Option | Description | Selected |
|--------|-------------|----------|
| Ambient shimmer on the range | Subtle motion, no text; never recolor a lit cell; LED-physics. | ✓ |
| Small labeled chip near range | ALL-CAPS chip (e.g., "UPDATING"); more intrusive. | |
| You decide (ui-phase) | Defer exact visual; lock behavior only. | |

**When it clears**

| Option | Description | Selected |
|--------|-------------|----------|
| On commit + 60s idle safety | Clears on commit; auto-clears after ~60s of no editing so a canceled edit doesn't stick. | ✓ |
| On commit only | Strictly on commit; canceled edit could linger. | |

**Notes:** The 60s idle safety mirrors ARCHITECTURE's soft-lock window. admin_editing heartbeat
shape/debounce/TTL left to Claude's discretion.

---

## Stale-highlight behavior (RTM-01)

**On a live move of the visitor's current record**

| Option | Description | Selected |
|--------|-------------|----------|
| Highlight follows the record | Re-run locate on boundary_changed affecting the active selection; highlight relocates. | ✓ |
| Clear with a gentle "moved — search again" cue | Drop stale highlight; prompt re-search. | |
| Keep highlight, refresh cube data only | Leave highlight (can point at wrong cube). | |

**How the move presents**

| Option | Description | Selected |
|--------|-------------|----------|
| Re-glow at the new cube | Fade old cube off, spring new on (LED-physics); cheap on Pi. | ✓ |
| Glide highlight across to new cube | Animate travel; heavier per-frame; jank risk. | |
| You decide (ui-phase) | Lock follow behavior; defer transition. | |

**Notes:** "Follow the record" requires invalidating the active `['locate', release_id]` query —
an extension to ARCHITECTURE's consumer sketch, which only invalidates `['cube', ...]`/admin keys.

---

## Optimistic edit + rollback feel (RTM-03)

**On server rejection**

| Option | Description | Selected |
|--------|-------------|----------|
| Revert + toast + keep values for retry | Grid snaps back; plain-language toast; editor keeps attempted values (reuse pendingChangeSet). | ✓ |
| Silent revert + toast only | Grid snaps back; editor cleared. | |
| Revert, no toast | Grid snaps back; no message. | |

**Cross-device optimistic behavior**

| Option | Description | Selected |
|--------|-------------|----------|
| Owner-device-local only | Optimistic apply local to editing device; kiosk/2nd-admin update only on committed boundary_changed. | ✓ |
| Broadcast optimistically to all | Push to kiosk immediately, un-apply on reject; flicker risk. | |

**Notes:** The kiosk still shimmers via admin_editing during the edit; it just doesn't re-render
boundary *data* until commit.

---

## Connectivity scope line (this phase vs deferred Offline slice)

**How much connection-state to build**

| Option | Description | Selected |
|--------|-------------|----------|
| Channel + sseConnected + reconnect resync | Build channel + sseConnected flag + resync; no visible offline UX. | ✓ |
| Also pull a minimal offline banner forward | Add basic banner now (bleeds deferred slice scope). | |
| Bare connection only | Don't track sseConnected here. | |

**Reconnect behavior (bus has no replay)**

| Option | Description | Selected |
|--------|-------------|----------|
| Resync boundary data on any reconnect | Invalidate `['units']`/`['cube',...]`/`['admin','cubes']` on every (re)connect; refetch settings on server_hello. | ✓ |
| Refetch only on server_hello | Resync only on server restart; misses transient kiosk-side blips. | |

**Notes:** This phase produces the `sseConnected` flag the deferred Offline slice consumes; the
banner/disabled-input/backoff/success-indicator/health-check all stay deferred.

---

## Claude's Discretion

- `admin_editing` heartbeat endpoint shape, payload, debounce (~250–500 ms), and ~60s server-side TTL.
- `boundary_changed` payload confirmation (`{cube_ids, change_set_id}`, one event per change-set).
- Multi-admin soft-lock specifics (last-write-wins + shimmer; no hard locking).
- EventBus internals (queue maxsize, slow-subscriber backpressure, unsubscribe cleanup).
- TanStack Query optimistic-mutation wiring (`onMutate`/`onError`/`onSettled`).
- Pi frame-budget validation for shimmer + re-glow (< 16 ms p95).
- All visual/interaction detail → `/gsd-ui-phase 4` within Nordic Grid.

## Deferred Ideas

- Offline Resilience (OFF-01..04) → next SPIDR slice.
- Privacy + Recently-Pulled (SRCH-09, PRIV-01..04) → later SPIDR slice.
- Multi-replica SSE fan-out (Redis/NATS) → not v1.
- MQTT-routed kiosk updates → rejected (Mosquitto is LED-only).
- Hard collaborative locking / CRDT → YAGNI for one operator.

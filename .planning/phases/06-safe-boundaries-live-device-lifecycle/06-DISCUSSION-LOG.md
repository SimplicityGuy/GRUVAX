# Phase 6: Safe Boundaries + Live Device Lifecycle - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-30
**Phase:** 6-Safe Boundaries + Live Device Lifecycle
**Areas discussed:** Edit-profile source, Revoke landing screen, Reassign UX, Write-isolation feedback

---

## Edit-profile source

| Option | Description | Selected |
|--------|-------------|----------|
| Browse-binding | profile_id resolved server-side from gruvax_browse_binding cookie; owner picks profile via existing /select; zero new UI | ✓ |
| Explicit profile param | Admin frontend sends profile_id per request; requires a profile selector in admin shell (new UI, conflicts with UI-hint:no) | |
| Default-profile only (defer) | Scope all writes to default profile UUID; closes hazard but no cross-profile admin editing yet | |

**User's choice:** Browse-binding
**Notes:** Follow-ups — (a) unbound admin → block with 400 session_unbound + route to /select (NOT default fallback); (b) all six write_boundary call sites + their boundary_changed fan-out scoped this phase, grep-verified.

---

## Revoke landing screen

| Option | Description | Selected |
|--------|-------------|----------|
| /pair, brief notice first | ~2–3s "screen removed — re-pair" notice then route to /pair | ✓ |
| /pair, instant redirect | Jump straight to /pair, no message | |
| /select (profile picker) | Route to picker instead of pairing | |

**User's choice:** /pair, brief notice first
**Notes:** Captured as implementation decisions — terminal 403 device_revoked from any in-flight call routes to the same handler as the SSE event (Phase 9 depends on this); kiosk tears down dead binding/SSE on exit.

---

## Reassign UX

| Option | Description | Selected |
|--------|-------------|----------|
| Brief "Moved to <Profile>" flash | Re-fetch session, reconnect SSE, refresh grid, ~2–3s toast naming new profile | ✓ |
| Silent live swap | Re-bind and refresh, no message | |
| Full-screen transition | "Switching to <Profile>…" interstitial during re-fetch | |

**User's choice:** Brief "Moved to <Profile>" flash
**Notes:** Plan-time check flagged — confirm GET /api/session returns the profile display name for the flash; add a follow-up fetch if it returns only the id. (Reassign event lands on OLD profile's bus, payload carries only device_id.)

---

## Write-isolation feedback

| Option | Description | Selected |
|--------|-------------|----------|
| 404 + UI refetch | 0-row write → 404; UI shows error + refetches grid; loud-fail | ✓ |
| 409 conflict | Return 409 + prompt reload | |
| Silent no-op (200) | Treat 0 rows as success | |

**User's choice:** 404 + UI refetch
**Notes:** Bulk writes / change-sets stay transactional — any 0-row match aborts the whole tx (no partial application). admin_editing shimmer events also retargeted to the resolved profile's bus for consistency (no cross-profile SSE leak).

---

## Claude's Discretion

- Exact wording/styling of the revoke notice and reassign flash (Nordic Grid tokens).
- Whether the revoke notice is tappable-to-skip vs. fixed timer.
- Mechanism for threading the resolved profile_id through the 6 call sites (shared dependency vs. per-route resolve), as long as every write + fan-out is covered.

## Deferred Ideas

- Dedicated admin profile-selector UI for boundary editing (decoupled from browse-binding) — rejected for this phase; revisit only if owners report friction switching via /select.

# Phase 9: Offline + Reconnect UX - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-01
**Phase:** 9-Offline + Reconnect UX
**Areas discussed:** Banner copy & variants, Banner look & stacking, Degraded-mode scope, Reconnect feedback

---

## Banner copy & variants

### Variants
| Option | Description | Selected |
|--------|-------------|----------|
| Two variants | Use `navigator.onLine` as cosmetic hint: "No network…" vs "Can't reach GRUVAX…" | ✓ |
| One generic message | Single banner regardless of cause | |

**User's choice:** Two variants

### Wording
| Option | Description | Selected |
|--------|-------------|----------|
| Reassuring + auto | "No network — trying to reconnect…" / "Can't reach GRUVAX — trying to reconnect…" | ✓ |
| Plain status only | "No network connection" / "GRUVAX is unavailable" | |
| Action-oriented | "No network — check the connection" / "Can't reach GRUVAX — it may be restarting" | |

**User's choice:** Reassuring + auto
**Notes:** SSE state remains the authoritative trigger; `navigator.onLine` only selects which copy to show (PITFALLS 35).

---

## Banner look & stacking

### Treatment
| Option | Description | Selected |
|--------|-------------|----------|
| Distinct urgent style | StalenessBar structure/position + stronger/reversed token palette + connectivity icon | ✓ |
| Match StalenessBar yellow | Identical yellow-on-blue; only copy/icon differ | |
| Full-screen scrim | Dim whole kiosk with overlay | |

**User's choice:** Distinct urgent style
**Notes:** Full-screen scrim explicitly rejected — would hide the preserved last result OFF-02 wants kept visible.

### Stacking & dismissibility
| Option | Description | Selected |
|--------|-------------|----------|
| Top priority, persistent | Takes top slot, suppresses other transient banners/pills, not dismissible, clears on reconnect | ✓ |
| Stack above, persistent | Sits above others without hiding them | |
| Top priority, dismissible | Top slot but visitor can dismiss | |

**User's choice:** Top priority, persistent

---

## Degraded-mode scope

### Scope of lockdown
| Option | Description | Selected |
|--------|-------------|----------|
| Lock all server-dependent | Disable search + profile-switch + cube taps; keep local/visual (highlight, RecentlyPulled) | ✓ |
| Search input only | Literal OFF-02 — only disable search box | |
| Full freeze | Disable every interaction | |

**User's choice:** Lock all server-dependent

### Search affordance
| Option | Description | Selected |
|--------|-------------|----------|
| Greyed + placeholder swap | Dimmed/non-focusable input, placeholder → "Search unavailable while offline" | ✓ |
| Greyed + lock icon | Dimmed input with lock/offline icon, placeholder unchanged | |
| You decide | Defer exact affordance to planner/UI-SPEC | |

**User's choice:** Greyed + placeholder swap

---

## Reconnect feedback

| Option | Description | Selected |
|--------|-------------|----------|
| Brief "Back online" toast | Banner clears + ~2–3 s SyncToast confirmation on `server_hello` | ✓ |
| Silent clear | Banner disappears, no confirmation | |
| Toast only after long outage | Silent for short blips, toast after longer outage (needs threshold) | |

**User's choice:** Brief "Back online" toast

---

## Claude's Discretion

- Exact placeholder/affordance string and the precise urgent-palette token choice (within Nordic Grid tokens / UI-SPEC).
- Whether a `/api/health` probe supplements SSE auto-reconnect for OFF-03 (default: SSE auto-reconnect + jitter alone; add probe only if needed).

## Deferred Ideas

- Admin / mobile-UI offline treatment — kiosk-only this phase per ROADMAP success criteria.
- Reconnect-toast outage-duration threshold (silent < ~10 s, toast after longer) — set aside in favor of always showing the toast.

# Phase 3: Admin Loop (PIN + Manual Entry + Undo) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-20
**Phase:** 3-admin-loop-pin-manual-entry-undo
**Areas discussed:** Admin access & session, Boundary editing model, Diff preview + undo, Kiosk reveal features, Kiosk admin input + Settings scope

---

## Admin access & session

### PIN format
| Option | Description | Selected |
|--------|-------------|----------|
| 6-digit numeric | 10-key keypad covers it; ~1M combos | |
| 4-digit numeric | Fastest to tap, smaller keypad, 10k combos | ✓ |
| Alphanumeric (4–12 chars) | Strongest, needs full in-app letter board | |

**User's choice:** 4-digit numeric
**Notes:** Accepting the weaker combo space; failed-attempt lockout was elevated in importance as a result.

### First-PIN provisioning
| Option | Description | Selected |
|--------|-------------|----------|
| Bootstrap CLI command | `gruvax set-pin` → Argon2id into `gruvax.settings`; plaintext never in env/git | ✓ |
| First-run setup screen | `/admin` creates PIN if none exists; deploy→first-PIN window unprotected | |
| Env var PIN_HASH at deploy | Hash offline, paste into `.env`; Change-PIN can't write back | |

**User's choice:** Bootstrap CLI command
**Notes:** Resolves the project's long-carried open question — PIN hash lives in `gruvax.settings`, set by CLI.

### Safety affordances in v1 (multi-select)
| Option | Description | Selected |
|--------|-------------|----------|
| Failed-attempt lockout | Rate-limit login; cooldown after N wrong PINs | ✓ |
| Change PIN | Settings row; requires current PIN; revokes other sessions (Pitfall 12) | ✓ |
| Lock button | Re-show PIN without ending session (Pitfall 23) | ✓ |
| Hard session cap | Force re-PIN after max lifetime regardless of activity (Pitfall 23) | ✓ |

**User's choice:** All four
**Notes:** All small and research-recommended; shipped together.

### Idle timeout + behavior mid-edit
| Option | Description | Selected |
|--------|-------------|----------|
| 10 min idle, preserve edits | Uncommitted edits survive in Zustand; re-PIN to commit | ✓ |
| 5 min idle, preserve edits | Tighter window, same preservation | |
| 10 min idle, discard edits | Clear pending change-set on timeout | |

**User's choice:** 10 min idle, preserve edits
**Notes:** 60s countdown still mandatory (ADMN-02). Edits live client-side, so nothing reaches DB until commit.

---

## Boundary editing model

### Edit structure
| Option | Description | Selected |
|--------|-------------|----------|
| Grid overview + per-cube editor | `/admin/cubes` read-only grid (fill levels) → tap → single-cube form | ✓ |
| Single-cube picker only | Pick from a list, no grid map | |
| Fully editable grid | Inline-edit all 32 cubes on one screen | |

**User's choice:** Grid overview + per-cube editor
**Notes:** Matches ROADMAP criterion 2 + ARCHITECTURE route tree; bulk reshuffle stays Phase 6.

### Autocomplete
| Option | Description | Selected |
|--------|-------------|----------|
| Two-step dependent | Label first, then catalog# filtered to that label | ✓ |
| Single combined field | One field matching label+catalog together | |
| Catalog-first | Type catalog#, infer label | |

**User's choice:** Two-step dependent
**Notes:** Source `v_collection` only; mirrors shelf ordering; reduces phantoms.

### Phantom / free-text handling
| Option | Description | Selected |
|--------|-------------|----------|
| Block + near-misses + override | Block save, show trigram near-misses, explicit "use anyway" | ✓ |
| Hard reject (no override) | Boundary must be a currently-owned record, no exceptions | |
| Warn-only, save proceeds | Save with a warning flag | |

**User's choice:** Block + near-misses + override
**Notes:** Single flow satisfies ADMN-03 + ADMN-06 + the sold-record edge (Pitfall 6).

### Suggest midpoint surfacing
| Option | Description | Selected |
|--------|-------------|----------|
| Inline button, always available | In per-cube editor between adjacent populated cubes | ✓ |
| Inline, only on empty/new boundaries | Auto-offer only when field empty | |
| Manual trigger only, never proactive | On-demand only | |

**User's choice:** Inline button, always available
**Notes:** Index-space walk (Pitfall 22); editable; never auto-applied.

---

## Diff preview + undo

### Diff content
| Option | Description | Selected |
|--------|-------------|----------|
| Mini-grid + before/after values | Affected cubes highlighted + per-cube old→new | ✓ |
| Mini-grid highlight only | Spatial only, no values | |
| Field-level list only | Text diff, no grid | |

**User's choice:** Mini-grid + before/after values

### Impact quantification
| Option | Description | Selected |
|--------|-------------|----------|
| Show record-movement counts | Compute redistribution from snapshot; flags emptied/overfull | ✓ |
| Values + highlighted cubes only | No record recomputation | |

**User's choice:** Show record-movement counts
**Notes:** Cheap (in-memory snapshot); strong safety net + differentiator.

### Revert granularity
| Option | Description | Selected |
|--------|-------------|----------|
| Whole change-set only | One save = one undo unit; inverse change-set | ✓ |
| Change-set + per-cube | Also revert single cube within a change-set | |

**User's choice:** Whole change-set only
**Notes:** Matches ADMN-09; revert is itself undoable.

### Revert conflict handling
| Option | Description | Selected |
|--------|-------------|----------|
| Block conflicts, revert the rest | Skip + report cubes a newer change-set touched | ✓ |
| Block whole revert on any conflict | Refuse entirely if any conflict | |
| Revert all (last-write-wins) | Overwrite newer edits | |

**User's choice:** Block conflicts, revert the rest
**Notes:** No silent clobber; inverse change-set records exactly what it touched.

---

## Kiosk reveal features

### Fill level meaning
| Option | Description | Selected |
|--------|-------------|----------|
| % of nominal capacity | records-in-range ÷ admin-set capacity; flags overstuffed | ✓ |
| Relative to fullest cube | Normalize to busiest cube; no absolute signal | |
| Raw record count only | Just the number | |

**User's choice:** % of nominal capacity
**Notes:** Capacity becomes an admin Settings value.

### Reverse-lookup subset
| Option | Description | Selected |
|--------|-------------|----------|
| First, last, + evenly sampled | first/last + ~6–8 sampled + total count | ✓ |
| First N in order | First ~10 + count | |
| Full scrollable list | Every record | |

**User's choice:** First, last, + evenly sampled

### Visibility
| Option | Description | Selected |
|--------|-------------|----------|
| Public on the kiosk | Anyone at the kiosk can see fill + contents | ✓ |
| Admin-gated | Only when logged in | |

**User's choice:** Public on the kiosk
**Notes:** Matches "visiting friends"; nothing sensitive; LAN-only.

### Empty cube tap
| Option | Description | Selected |
|--------|-------------|----------|
| Gentle message + admin shortcut | "No records assigned yet" + editor shortcut if admin | ✓ |
| Message only, no shortcut | Message for all, no shortcut | |
| Not tappable | Empty cubes don't respond | |

**User's choice:** Gentle message + admin shortcut

---

## Kiosk admin input + Settings scope

### Kiosk input strategy
| Option | Description | Selected |
|--------|-------------|----------|
| Tap-to-pick lists, no letter board | Label list (A–Z rail) → scoped catalog#s; numeric keypad for PIN/filter | ✓ |
| Build the in-app letter board | ~80-line full alphabetic keyboard for type-to-filter | |
| Mobile-only editing, kiosk = view + revert | Conflicts with ROADMAP criterion 1 | |

**User's choice:** Tap-to-pick lists, no letter board
**Notes:** Resolves the keypad-vs-letters tension surfaced after the 4-digit PIN choice; phantoms impossible by construction on kiosk; mobile uses real keyboard with same components.

### Settings page scope (this phase)
| Option | Description | Selected |
|--------|-------------|----------|
| Minimal: PIN + capacity + idle TTL | Only what this phase introduces | ✓ |
| Just Change PIN | Hardcode capacity + idle TTL | |
| Full settings shell now | Build whole shell incl. placeholder color rows | |

**User's choice:** Minimal: PIN + capacity + idle TTL
**Notes:** LED color/brightness deferred to Phase 5.

---

## Claude's Discretion

- Lockout policy numbers, hard-cap duration (~30 min), idle default (10 min).
- Cookie/CSRF specifics (HttpOnly, Secure, SameSite=Strict), session-token entropy.
- Trigram near-miss similarity threshold (reuse Phase 2 `pg_trgm` path).
- Nominal cube capacity default (~90–100) + fill-level token mapping.
- Evenly-sampled subset size (~6–8) + sampling method (index-stride).
- Alembic 0004 migration for admin tables (Phase 1 conventions).
- All visual/interaction design → `/gsd-ui-phase 3`.

## Deferred Ideas

- SSE cross-device live admin refresh + `admin_editing` soft-lock → Phase 4 (KNOWN LIMITATION this phase).
- CSV/YAML import + reshuffle wizard → Phase 6.
- `boundaries.yaml` export → Phase 6.
- LED color/brightness/diagnostic settings + panic-off → Phase 5.
- Recently-pulled / privacy floors → Phase 4.
- Per-visitor PIN → v2 (out of scope).
- Owner-curated real golden positions (closes Phase 2 D-08) → Phase 6 / post-reshuffle.
- Per-cube partial revert → considered, deferred.

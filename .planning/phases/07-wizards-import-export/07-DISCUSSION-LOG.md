# Phase 7: Wizards + Import/Export - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-24
**Phase:** 7-wizards-import-export
**Areas discussed:** Wizard model & flow, Reshuffle resume / persistence, Import format & semantics, Export + settings round-trip

---

## Wizard model & flow

| Option | Description | Selected |
|--------|-------------|----------|
| One engine, two modes | Single `/admin/wizard` with fresh-setup + reshuffle modes; same step UI/commit | ✓ |
| Two separate flows | Distinct setup/reshuffle components; more duplication, drift risk | |

| Option | Description | Selected |
|--------|-------------|----------|
| Cut points only | Wizard walks collecting first record per cube; overrides stay in segment editor | ✓ |
| Cut points + optional overrides | Wizard also offers per-bin override step; heavier branching flow | |

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse RecordPickerSheet + mark empty | Phase 5 picker (autocomplete + phantom-block) per step + empty/skip control | ✓ |
| Lightweight inline picker, no empty control | Slimmer input, can't represent gaps, reimplements validation | |

| Option | Description | Selected |
|--------|-------------|----------|
| Add distinct sources | Migration 0007 adds `wizard`/`reshuffle`/`csv`/`yaml` to source CHECK; legible history | ✓ |
| Reuse 'bulk' for all | No migration; every multi-cube commit shows as 'bulk' | |

**User's choice:** One engine/two modes; cut points only; RecordPickerSheet + mark-empty; add distinct sources.
**Notes:** SC1's "single point of transition" reconciled to the Phase 5 cut-point model — wizard sets first record per cube, last derived.

---

## Reshuffle resume / persistence

| Option | Description | Selected |
|--------|-------------|----------|
| After every step | Persist draft to localStorage on each confirmed cube; loss window = 1 cube | ✓ |
| Debounced / periodic | Timer/debounced save; wider loss window, more moving parts | |

| Option | Description | Selected |
|--------|-------------|----------|
| Re-validate on resume, flag stale | Re-run draft through cubes/validate; flag stale cuts with trigram fix | ✓ |
| Resume as-is, validate at commit | Restore verbatim; rely on commit-time validate | |

| Option | Description | Selected |
|--------|-------------|----------|
| Clear on commit + explicit Discard, no auto-expiry | Remove on commit; banner has Discard (confirm); no time expiry | ✓ |
| Add auto-expiry (e.g. 7 days) | Also drop old drafts automatically; risks discarding a paused reshuffle | |

**User's choice:** Save every step; re-validate on resume; clear on commit or explicit discard, no auto-expiry.
**Notes:** Nothing reaches the DB until the final atomic commit.

---

## Import format & semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Both CSV and YAML | Accept either, parse to one internal cut-point model | ✓ |
| YAML only | Single format, clean round-trip; CSV needs manual conversion | |
| CSV only | Spreadsheet-native; awkward for nested settings/overrides | |

| Option | Description | Selected |
|--------|-------------|----------|
| Full replace-all, atomic | File = complete desired set; one revertible change-set | ✓ |
| Per-row merge | Only present cubes updated; breaks round-trip identity | |

| Option | Description | Selected |
|--------|-------------|----------|
| Cut point + is_empty + overrides | Full boundary state; lossless backup/restore; overrides optional on import | ✓ |
| Cut point + is_empty only | Simpler; loses manual overrides on restore | |

| Option | Description | Selected |
|--------|-------------|----------|
| Any error blocks commit; show all rows to fix | validate per-row + trigram + diff; commit disabled until clean | ✓ |
| Commit valid rows, report skipped | Partial commit; contradicts atomic replace | |

**User's choice:** Both CSV+YAML; full atomic replace-all; cut point + is_empty + overrides; any error blocks commit.
**Notes:** `/admin/import` preview reuses the `cubes/validate` endpoint output (movement counts + mini-grid).

---

## Export + settings round-trip

| Option | Description | Selected |
|--------|-------------|----------|
| YAML + JSON | Export both serializations of one schema | |
| YAML only | Single canonical export; matches ARCHITECTURE endpoint; CSV import-only | ✓ |

| Option | Description | Selected |
|--------|-------------|----------|
| Validated PUT, no change-set | Settings import validates + applies via settings path; no boundary_history | ✓ |
| Preview + confirm before apply | Show before/after diff of settings keys; more ceremony | |

| Option | Description | Selected |
|--------|-------------|----------|
| LED/presentation only; never auth | Export/import led_*/UI keys; hard-exclude auth.pin_hash & secrets | ✓ |
| All non-secret settings | Broader config backup; blurs BAK-02 framing | |

**User's choice:** Export YAML only; settings import = validated PUT (no change-set); LED/presentation keys only, auth hard-excluded.
**Notes:** PIN hash never serialized to a downloadable file (Pitfall 12).

---

## Claude's Discretion

- Verify `cubes/bulk` speaks the cut-point shape post-Phase-5; extend if needed.
- Wizard end-of-shelf cut overflow behavior (carry Phase 5 D-06 edge).
- Exact CSV column layout (flat, overrides omitted) vs YAML nested schema (with overrides).
- Confirmation surface (inline toast vs dedicated screen).
- Wizard step navigation (back/skip, progress, LocatorHeader position).
- Idempotency-Key generation; admin nav entry points; all UI polish → `/gsd-ui-phase 7`.

## Deferred Ideas

- Versioned/named boundary snapshots; animated reshuffle preview (backlog).
- JSON boundary export (YAML is canonical in v1).
- Width-override authoring inside the wizard (stays in segment editor).
- Density-imbalance-driven reshuffle suggestion (future-tier).
- Automatic git commit / cloud-sync of boundary state (permanently out of scope).

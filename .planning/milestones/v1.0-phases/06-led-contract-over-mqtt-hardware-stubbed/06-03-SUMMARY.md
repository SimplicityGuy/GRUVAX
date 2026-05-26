---
phase: 06-led-contract-over-mqtt-hardware-stubbed
plan: "03"
subsystem: admin-led-settings
tags: [led, admin, settings, color-blind, tdd, frontend, backend]
dependency_graph:
  requires: ["06-01"]
  provides: ["led-settings-persistence", "admin-led-ui", "colorblind-preview"]
  affects: ["06-04"]
tech_stack:
  added: []
  patterns:
    - "FastAPI dependency_overrides for unit testing without live DB"
    - "React color picker + preset swatches + colorblind simulation row"
    - "Matrix math color-blind simulation (Vienot 1999) — zero new deps"
    - "LED key naming contract D-24: span=label-span tier, ambient=idle baseline"
key_files:
  created:
    - tests/unit/test_led_color.py
    - tests/unit/test_admin_led_settings.py
    - frontend/src/components/ColorBlindPreview.tsx
    - frontend/src/lib/colorblind.ts
  modified:
    - src/gruvax/api/admin/settings.py
    - frontend/src/api/types.ts
    - frontend/src/routes/admin/Settings.tsx
    - frontend/src/routes/admin/admin.css
decisions:
  - "Separated simulateColorBlindness into src/lib/colorblind.ts so ColorBlindPreview.tsx only exports components (react-refresh/only-export-components lint rule)"
  - "Used app.dependency_overrides[require_admin] pattern for unit tests — patching the module attribute does not intercept FastAPI dependency injection"
  - "Added lib/colorblind.ts with git add -f because .gitignore has a bare lib/ rule (Python virtualenv artifact); existing lib/ files were already tracked, this file belongs to the same directory"
  - "HTTP_422_UNPROCESSABLE_CONTENT used instead of deprecated HTTP_422_UNPROCESSABLE_ENTITY"
metrics:
  duration: "~25 minutes (tasks 1-3)"
  completed_date: "2026-05-23"
  tasks_completed: 3
  tasks_total: 3
  files_changed: 8
---

# Phase 6 Plan 03: Admin LED Settings UI + Backend Extension Summary

Admin LED configuration vertical slice: six per-state color pickers with colorblind simulation previews, three brightness sliders (span/active/ambient per D-24 naming), highlight TTL/retain lifecycle controls in the existing Settings page, plus backend extension of GET/PUT `/api/admin/settings` to persist all 12 LED keys and refresh the settings cache.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | TDD test scaffold — LED color math + admin settings | `31c8cb3` | tests/unit/test_led_color.py, tests/unit/test_admin_led_settings.py |
| 2 (GREEN) | Backend extension — admin/settings GET/PUT LED keys | `387fa71` | src/gruvax/api/admin/settings.py |
| 3 (GREEN) | Frontend UI — LEDs section, ColorBlindPreview, CSS | `e6aaaf3` | frontend/src/components/ColorBlindPreview.tsx, frontend/src/lib/colorblind.ts, frontend/src/api/types.ts, frontend/src/routes/admin/Settings.tsx, frontend/src/routes/admin/admin.css |

## What Was Built

**Backend (`src/gruvax/api/admin/settings.py`):**
- Extended `_ALLOWED_SETTINGS_KEYS` frozenset from 2 to 14 keys (6 colors, 3 brightness tiers, 3 lifecycle)
- Key naming enforces D-24: `led_brightness.span` = label-span tier (~50%), `led_brightness.ambient` = idle baseline — NEVER conflated
- Hex color validation via `_HEX_COLOR_RE` regex; raises HTTP 422 for malformed values
- Color stored as JSON strings `'"#RRGGBB"'`; int/bool stored as bare JSON primitives
- `load_settings_cache(pool)` called after all writes (D-15 cache refresh)
- Top-level import for `load_settings_cache` (was lazy — required for test patching)

**Frontend (`frontend/src/`):**
- `components/ColorBlindPreview.tsx` — renders DEUTAN/PROTAN/TRITAN swatches using CSS class `colorblind-preview`
- `lib/colorblind.ts` — `simulateColorBlindness(hex, type)` + Vienot 1999 matrices verbatim from RESEARCH.md; CB_TYPES array; zero new packages
- `api/types.ts` — extended `AdminSettings` and `AdminSettingsPut` with 12 optional LED fields; inline comments document D-24 naming contract
- `routes/admin/Settings.tsx` — added `handleSaveLeds` calling `putAdminSettings` with all 12 fields; LEDs section with: 6 color pickers each with Nordic Grid preset swatches (#0051A2, #FFDA00, #F7F9FC) and ColorBlindPreview; 3 brightness range sliders with mono value badge; highlight TTL input; retain mode toggle with conditional retain timeout; `settings-actions--leds` div stub for Plan 06-04 buttons
- `routes/admin/admin.css` — added CSS for `.settings-color-row`, `.settings-color-input`, `.settings-color-presets`, `.settings-color-preset-btn`, `.colorblind-preview*`, `.settings-range-row`, `.settings-range-input`, `.settings-value-mono`, `.settings-toggle`; all colors via `var(--gruvax-*)` tokens

## Test Results

```
8 passed (tests/unit/test_admin_led_settings.py: 6, tests/unit/test_led_color.py: 2)
214 passed total (2 pre-existing failures: test_cache_load_from_db, test_snapshot_load_from_db — require live DB, not caused by this plan)
mypy --strict: no issues found in 47 source files
npm run build: tsc -b && vite build — success (0 TypeScript errors)
eslint: no issues on touched files
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `load_settings_cache` not patchable in tests**
- **Found during:** Task 1 (RED tests failed with AttributeError when patching)
- **Issue:** Original `settings.py` imported `load_settings_cache` lazily inside the handler function body; `unittest.mock.patch("gruvax.api.admin.settings.load_settings_cache")` failed because the name didn't exist at module level
- **Fix:** Moved `from gruvax.db.queries import load_settings_cache` to module-level import
- **Files modified:** src/gruvax/api/admin/settings.py
- **Commit:** `387fa71`

**2. [Rule 1 - Bug] react-refresh lint error for non-component export**
- **Found during:** Task 3 (ESLint check after writing ColorBlindPreview.tsx)
- **Issue:** `simulateColorBlindness` exported from the same file as the `ColorBlindPreview` component triggered `react-refresh/only-export-components` error
- **Fix:** Extracted matrix math to `frontend/src/lib/colorblind.ts`; `ColorBlindPreview.tsx` now only exports the component
- **Files modified:** frontend/src/components/ColorBlindPreview.tsx (rewritten), frontend/src/lib/colorblind.ts (new)
- **Commit:** `e6aaaf3`

**3. [Rule 3 - Blocking] `lib/` gitignored by Python virtualenv pattern**
- **Found during:** Task 3 git staging
- **Issue:** `.gitignore` has a bare `lib/` rule (Python pattern); `frontend/src/lib/colorblind.ts` was blocked from staging even though `frontend/src/lib/dom.ts` and `shelf.ts` are already tracked
- **Fix:** Used `git add -f frontend/src/lib/colorblind.ts` since the directory is already tracked
- **Commit:** `e6aaaf3`

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| RED (`test(...)`) | `31c8cb3` | PASS — 8 tests fail before implementation |
| GREEN (`feat(...)` backend) | `387fa71` | PASS — all 8 tests pass |
| GREEN (`feat(...)` frontend) | `e6aaaf3` | PASS — build + lint clean, all tests still pass |

## Known Stubs

None — all LED fields are fully wired from the Settings form through `putAdminSettings` to the backend DB and cache. The `settings-actions--leds` div is an intentional placeholder for Plan 06-04's "All Off" and "Run Diagnostic" buttons (documented in JSX comment).

## Threat Flags

None — no new network endpoints introduced. The LED settings are stored under existing PUT `/api/admin/settings` behind the existing admin auth guard. No new trust boundaries.

## Self-Check: PASSED

- `frontend/src/components/ColorBlindPreview.tsx` — FOUND
- `frontend/src/lib/colorblind.ts` — FOUND
- `src/gruvax/api/admin/settings.py` — FOUND (modified)
- `frontend/src/api/types.ts` — FOUND (modified)
- `frontend/src/routes/admin/Settings.tsx` — FOUND (modified)
- `frontend/src/routes/admin/admin.css` — FOUND (modified)
- Commit `31c8cb3` — FOUND
- Commit `387fa71` — FOUND
- Commit `e6aaaf3` — FOUND

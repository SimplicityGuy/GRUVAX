---
status: resolved
phase: 03-admin-loop-pin-manual-entry-undo
source: hands-on UAT (2026-05-21)
app_under_test: local uvicorn :8001 against dev Postgres (152 collection rows, 32 cube boundaries, 41 history)
resolution: F1–F7 fixed and verified (live + full test suite); F8 deferred (overlaps WR-03). See 03-UAT-FIXES.md.
---

## Resolution (2026-05-21)

F1–F7 are fixed, committed, and verified — F1/F2/F3 live, F4/F5/F6/F7 live in the corrected
diff-preview + editor and via the full backend suite (EXIT 0), ruff/mypy clean, frontend build
clean. Fix details in `03-UAT-FIXES.md`. F8 (deep-link re-prompt) deferred — overlaps the
already-deferred WR-03 session-rehydration; re-entering the PIN continues the same server session.

**Process note (not a product bug):** the backend integration tests run against the *dev*
Postgres and overwrite `gruvax.settings.auth.pin_hash` + create many `admin_sessions`/
`boundary_history` rows (448 sessions / 41 history seen). After any `uv run pytest`, the admin
PIN is no longer the dev value — re-run `gruvax-set-pin` before manual UAT. Consider a dedicated
test DB / transactional rollback fixture in a future hardening pass.


# Phase 3 — Hands-on UAT Findings

Live click-through of the admin loop surfaced the issues below. None are data-corrupting
(the server enforces `first>last` + phantom checks even when the client doesn't gate COMMIT),
but several are real UX defects. The shipped automated tests passed because they mock routing
(frontend) and test the API in isolation (backend) — these only appear when the real SPA talks
to the real server.

## UAT pass/fail by item

| # | Item | Result |
|---|------|--------|
| 1 | PIN login → shell + countdown | PASS (live) |
| 4 | Cube editor + autocomplete | PASS (structure live; backend tested) |
| 5 | Phantom block + near-misses + USE ANYWAY | PASS functionally; alert misplaced (F7) |
| 6 | Suggest midpoint | code-verified |
| 7 | Diff preview + commit | bugs F4/F5/F6 |
| 8 | History + revert + undoable inverse | PASS (live) |
| 10 | Kiosk fill bars + contents panel | PASS (live) |
| 2 | Countdown <60s warning + aria-live | code-verified; needs human watch |
| 3 | Lock / Logout | buttons wired; needs human click-test |
| 9 | Conflict-aware revert | code-verified (server has_newer_changes; UNDO entries present) |

## Findings

### F1 — SPA deep-links 404 (FIXED)
`StaticFiles(html=True)` only serves `index.html` for directory requests, so `/admin`,
`/admin/cubes`, `/admin/history`, `/admin/cubes/:u/:r/:c` returned a JSON 404 — breaking
mobile admin access and browser refresh (ADMN-01). Fixed in `src/gruvax/app.py`
(`SpaStaticFiles.get_response` now catches Starlette's 404 and serves `index.html` for
extensionless routes; real missing assets still 404). Verified: those routes now return 200.

### F2 — `gruvax-set-pin` CLI broken
`uv run gruvax-set-pin` fails with `ModuleNotFoundError: No module named 'scripts'` — the
console-script entry point `scripts.set_pin:main` is not importable in the installed env
(the `scripts` package isn't packaged). D-02's documented bootstrap path does not run.
Fix: make the entry point resolvable (move the CLI under `src/gruvax/` or include `scripts`
in the build/packaging), keep `uv run gruvax-set-pin` working.

### F3 — compose.yaml does not pass SESSION_SECRET to the API
The Phase 3 code requires `SESSION_SECRET` (no default — crash on missing), but the
`gruvax-api` service in `compose.yaml` has no `env_file:`/`environment` entry for it. A
rebuilt container crashes on boot. Fix: add `env_file: .env` (or an explicit
`SESSION_SECRET: "${SESSION_SECRET}"`) to the `gruvax-api` service.

### F4 — Commit error surfacing + no client-side gate
`DiffPreviewSheet.handleCommit` `catch` shows a generic "Could not save — check your
connection and try again." for ALL failures, including the server's structured 400
(`boundary_order_error`, `phantom_boundary`). COMMIT is only `disabled` on
`isCommitting/isValidating`, never on validate results, and the validate dry-run error is
silently swallowed (`.catch(() => setIsValidating(false))`). Result: a user who commits an
out-of-order or phantom set sees a misleading connection error with no path to fix.
Fix: surface the server's `message` (order/phantom) on commit failure, and ideally block
COMMIT (or warn) when the validate dry-run reports invalid.

### F5 — Diff table missing BEFORE column
`DiffPreviewSheet` renders only `FIELD | AFTER`; D-09 requires per-cube before→after.
The validate result carries prior state (used for movement counts) but the before boundary
values are not shown. Fix: add a BEFORE column populated from the current boundary.

### F6 — Cube address 0-vs-1-indexed inconsistency
`CubesGrid`/`CubeEditor` display 0-indexed addresses (`1/0/2`), but `DiffPreviewSheet`'s
`cubeAddress()` and mini-grid use `row+1`/`col+1` (`1/1/3`) for the SAME cube. The address
sent to the server is correct (no data impact) but the preview mislabels which cube changes.
Fix: one consistent scheme across grid, editor, and preview.

### F7 — Phantom near-miss alert rendered under the wrong record
Typing a phantom value into the LAST RECORD catalog renders the "Not in collection" alert +
near-miss chips under the FIRST RECORD section. Fix: render the phantom alert under the field
that triggered it.

### F8 (minor) — Deep-link/refresh re-prompts PIN with a valid session
A hard load of a protected route re-shows the PIN overlay instead of rehydrating from the
valid session cookie via `GET /api/admin/session`. Re-entering continues the same server
session, so not blocking. Overlaps the deferred WR-03 (session rehydration). Lower priority.

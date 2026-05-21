---
status: partial
phase: 03-admin-loop-pin-manual-entry-undo
source: [03-VERIFICATION.md]
started: 2026-05-20
updated: 2026-05-20
total_items: 10
passed: 0
---

# Phase 3 — Human UAT Checklist (Admin Loop)

All automated verification passed (41 tests green, tsc/ruff/mypy clean, builds clean, 5/5 must-haves backed by code). The items below are interactive/visual flows that only a human can confirm on the running app. Mark each `[x]` as you verify it; when all pass, re-run `/gsd:verify-work 3` (or `/gsd:plan-phase 3 --gaps` if something fails) to flip the phase to `passed`.

**Setup:** stack is up (`docker compose up -d`). Set a PIN first if you haven't: `set -a; source .env; set +a; uv run gruvax-set-pin` (after `alembic upgrade head`). Open the kiosk at the dev URL and `/admin` for the admin UI.

## Current Test
[awaiting human testing — start at item 1]

## Tests

- [ ] **1. PIN login end-to-end (mobile + kiosk)** — Open `/admin` on a phone-sized viewport and on the kiosk viewport. Tap the in-app keypad to enter the correct PIN.
  - Expected: admin shell loads (GRUVAX ADMIN wordmark, countdown pill, Lock + Log out icons); **no system keyboard appears** on the kiosk.
  - Why human: NumericKeypad tap feel + kiosk no-system-keyboard is the labwc/#2926 safety requirement. (ADMN-01)

- [ ] **2. Countdown pill — last-60s warning + aria-live** — Watch the header countdown after login; wait until <60s remain.
  - Expected: pill ticks mm:ss, turns `--gruvax-warning` color in the last 60s, screen reader announces via `aria-live="polite"`.
  - Why human: color + assistive-tech behavior. Note: initial value is hardcoded 10 min (WR-03, deferred) and self-corrects within 30s via the `/session` poll. (ADMN-02)

- [ ] **3. Lock / Logout** — Tap Lock → PIN overlay returns, session preserved; re-enter PIN → same countdown continues (not reset). Tap Logout → immediate, no confirm dialog.
  - Expected: Lock preserves session; Logout is immediate. (ADMN-08)

- [ ] **4. Two-step dependent autocomplete** — Open `/admin/cubes`, tap a cube. In the label field only collection labels appear; the catalog# field is disabled until a label is chosen, then lists only catalogs for that label.
  - Expected: autocomplete fed by `v_collection`, catalog scoped to label. (ADMN-03)

- [ ] **5. Phantom block + force path + comparator error** — Type a catalog# not in the collection → phantom warning with tappable near-miss chips; tap a chip to fill; tap "USE ANYWAY" → force mode set. Then set first_catalog after last_catalog → boundary-order error blocks preview/save.
  - Expected: phantom blocked w/ trigram near-misses; force path works; `first>last` rejected via POS-01. (ADMN-06)

- [ ] **6. Suggest midpoint — real record from index space** — For a cube between two populated cubes, tap "SUGGEST MIDPOINT". Cross-check the suggested record exists by searching for it on the kiosk.
  - Expected: a real owned record (index-space, Pitfall 22), pre-filled + editable, never auto-applied. (ADMN-12)

- [ ] **7. Diff preview + atomic commit + cache reload** — Edit a boundary (ADD TO PENDING) → PREVIEW CHANGES. Confirm the changed cube is ringed on the mini-grid with AFTER values + record-movement counts. COMMIT CHANGE SET → "Saved — change set {id}"; kiosk reflects the new boundary on next load.
  - Expected: diff preview correct; atomic commit + in-process cache reload. (ADMN-07, ADMN-09)

- [ ] **8. History + revert + undoable inverse** — `/admin/history` lists change-sets newest-first (short UUID, source badge, timestamp, cube count). REVERT one → destructive confirm → REVERTED pill, boundaries restored, and a new revert change-set appears (revert is itself undoable).
  - Expected: history list + one-tap revert + undoable inverse change-set. (ADMN-09)

- [ ] **9. Conflict-aware revert (no silent clobber)** — Commit change-set A (edit cube B1), then change-set B (edit B1 again), then REVERT A.
  - Expected: conflict banner names the skipped cube; B1 is NOT silently clobbered; non-conflicting cubes revert. (D-12)

- [ ] **10. Kiosk fill bars + cube contents panel (public)** — On the kiosk (no login): cubes with data show a fill bar (color thresholds: <80% blue-light, 80–100% yellow, >100% red). Tap a populated cube → bottom-sheet with address, count + fill%, FIRST/LAST records, ~7 samples. Tap an empty cube → "No records assigned to this cube yet". While logged in as admin → "EDIT THIS CUBE" shortcut appears.
  - Expected: public fill bars (CUBE-07) + contents panel (CUBE-09); D-16 admin shortcut gated on `isLoggedIn`.

## Deferred (tracked, non-blocking)
- **WR-03** — PinOverlay/countdown initial value fabricated; self-corrects via `/session` poll. Real fix needs `POST /login` to return `expires_at`/`hard_cap_at`.
- **WR-05** — Rate-limit key trusts `REMOTE_ADDR` (no proxy chain validation). Safe on single-host LAN; revisit if deployed behind a proxy (avoid blindly trusting `X-Forwarded-For` — SSRF risk).
- **WR-06** — Login rate-limiting uses `limits.FixedWindowRateLimiter` internals; revisit as a maintenance refactor under "always latest".

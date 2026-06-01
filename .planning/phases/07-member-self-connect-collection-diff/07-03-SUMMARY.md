---
phase: 07-member-self-connect-collection-diff
plan: 03
subsystem: frontend
tags: [react, auth, invite-codes, sse, kiosk, design-tokens, accessibility]

# Dependency graph
requires:
  - phase: 07-01
    provides: has_token, last_new_record_count, last_sync_is_initial on admin profiles API; collection_changed SSE payload extended
  - phase: 07-02
    provides: POST /api/admin/profiles/{id}/invite; GET /api/invite-codes/{code}; POST /api/invite-codes/{code}/redeem

provides:
  - RedeemPage at /redeem/:code (public, no PIN gate)
  - inviteClient.ts: getInviteCode + redeemInviteCode (publicFetch, credentials omit) + generateInvite (adminFetch)
  - ProfileDrawer INVITE LINK section: generate, TTL countdown, copy-to-clipboard
  - ProfileDiagnosticsCard NEW RECORDS / IMPORTED row driven by last_new_record_count
  - KioskView yellow new-records pill driven by collection_changed SSE payload

affects:
  - Human-verify checkpoint: 6 surfaces across admin + kiosk + public redeem page

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "publicFetch with credentials omit for public invite endpoints (T-07-13 — PAT never leaves POST body)"
    - "setInterval TTL countdown with cleanup in useEffect; color shifts via inline style with CSS token values"
    - "Defensive SSE payload parse: try/catch JSON.parse in collection_changed handler (T-07-16)"
    - "ESLint react-hooks/set-state-in-effect: disable only in synchronous effect early-return branches; async/.then() callbacks exempt"
    - "node_modules symlink worktree pattern: ln -sf main/node_modules worktree/node_modules for lint/typecheck"

key-files:
  created:
    - frontend/src/api/inviteClient.ts
    - frontend/src/routes/redeem/RedeemPage.tsx
    - frontend/src/routes/redeem/RedeemPage.css
    - frontend/public/gruvax-logo-icon.svg
  modified:
    - frontend/src/api/types.ts
    - frontend/src/api/adminClient.ts
    - frontend/src/App.tsx
    - frontend/src/routes/admin/ProfileDrawer.tsx
    - frontend/src/routes/admin/ProfileDiagnosticsCard.tsx
    - frontend/src/routes/kiosk/KioskView.tsx
    - frontend/src/routes/kiosk/kiosk.css

key-decisions:
  - "publicFetch uses credentials omit — public invite endpoints carry no session cookie and no CSRF (D-03)"
  - "RedeemPage uses mapRedeemError to map detail.type from backend uniform-404 responses to UI-SPEC copy"
  - "TTL countdown uses setInterval inside useEffect keyed on inviteInfo — interval cleared on cleanup and when inviteInfo becomes null"
  - "KioskView collection_changed handler upgraded from () to (e: MessageEvent) with defensive JSON.parse; gracefully degrades on empty/malformed payload (T-07-16)"
  - "/redeem/* exempted from session-bootstrap unbound redirect (D-03 — public route)"
  - "gruvax-logo-icon.svg copied to frontend/public/ for static file serving on the redeem page"
  - "node_modules symlink created in worktree frontend/ (worktree isolation pattern — removed after merge)"

patterns-established:
  - "ESLint set-state-in-effect: suppress only in synchronous effect body early-return guards; async callbacks in .then() / setInterval are exempt from the rule"

requirements-completed: [AUTH-02, API-04]

# Metrics
duration: ~60min
completed: 2026-06-01
---

# Phase 7 Plan 03: AUTH-02 + API-04 Frontend Summary

**Member self-connect UI (AUTH-02) and collection-diff indicators (API-04): public redeem page, owner invite affordance with TTL countdown + copy-to-clipboard, admin NEW RECORDS diagnostics row, and kiosk yellow new-records pill — all consuming the Plan 01/02 backend contracts, design-token-only, lint + typecheck clean.**

## Performance

- **Duration:** ~60 min
- **Started:** 2026-06-01T10:30:00Z
- **Completed:** 2026-06-01T11:30:00Z
- **Tasks:** 3 (2 auto + 1 checkpoint:human-verify — all complete)
- **Files modified:** 11 (4 created, 7 modified)

## Accomplishments

**Task 1: Types + invite client + public redeem page (AUTH-02 member UI)**

- `types.ts`: `AdminProfile` extended with `has_token`, `last_new_record_count`, `last_sync_is_initial`; new types `InviteCodeInfo`, `GeneratedInvite`, `RedeemResult`
- `inviteClient.ts`: `publicFetch` (credentials omit, no CSRF), `getInviteCode`, `redeemInviteCode` (throw `RedeemApiError` with errorType), `generateInvite` (adminFetch, PIN-gated)
- `RedeemPage.tsx`: 5-state machine (loading/active/invalid/submitting/success); PAT input with Eye/EyeOff toggle, yellow focus ring; `mapRedeemError` maps backend `detail.type` to UI-SPEC copy; terminal "CONNECTED" heading + "Your collection is importing" body; T-07-13 mitigations (autocomplete off, type=password)
- `RedeemPage.css`: mobile-first 390px baseline, min-height 100dvh, centered 480px card, token-only, fade-in animations, no hardcoded hex
- `App.tsx`: `/redeem/:code` route outside `/admin` nest; session bootstrap exempts `/redeem/*` from unbound-session redirect; `gruvax-logo-icon.svg` copied to `frontend/public/`

**Task 2: Owner invite affordance + admin diagnostics row + kiosk new-records pill (API-04)**

- `ProfileDrawer.tsx`: INVITE LINK section (drawerMode=view); setInterval TTL countdown with cleanup; color shifts to warning (<5min), error (<1min); `navigator.clipboard.writeText` with COPIED! feedback + clipboard-denied error copy; GENERATE INVITE LINK secondary button; no PAT ever shown to owner (T-07-14)
- `adminClient.ts`: `ProfileDiagnosticEntry` extended with `last_new_record_count: number | null` + `last_sync_is_initial: boolean | null`
- `ProfileDiagnosticsCard.tsx`: NEW RECORDS / IMPORTED row between ITEMS and LAST ERROR; `--gruvax-success` for count > 0, `--gruvax-text-muted` for zero/null; no yellow on admin cards
- `KioskView.tsx`: `collection_changed` handler upgraded to `(e: MessageEvent)` — defensive JSON.parse with try/catch; reads `new_record_count`, `is_initial_import`; verifies `profile_id` matches boundProfileId; updates `newRecordState`; yellow pill rendered below search box with `role="status"` `aria-live="polite"`
- `kiosk.css`: `.kiosk-new-records-pill` — yellow bg, blue-darker text, pill radius, Barlow Condensed 700 18px, fade-in animation; token-only

## Task Commits

1. **Task 1: Types + invite client + public redeem page** - `c321985` (feat)
2. **Task 2: Owner invite affordance + admin diagnostics row + kiosk new-records pill** - `64d8e6c` (feat)

## Checkpoint Status

**Task 3: Human-verify — APPROVED (gate=blocking)**

The developer verified all 6 surfaces against a live backend and reported no issues:
1. INVITE GENERATION in admin ProfileDrawer — verified (link box, TTL countdown, COPY LINK + COPIED!, single-active supersede)
2. REDEEM flow (member, incognito browser) — verified (CONNECT heading, PAT toggle, terminal CONNECTED state)
3. SINGLE-USE: reload the same /redeem URL after redemption — verified (plain-language error card, no form)
4. DIFF INDICATOR on admin diagnostics card — verified (IMPORTED / NEW RECORDS row)
5. KIOSK PILL after a sync — verified (yellow pill, clears/replaces on next sync)
6. No raw PAT visible anywhere in admin UI — verified (owner sees presence + invite URL only)

The plan is fully complete (3/3 tasks).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Added /redeem/* session-bootstrap redirect exemption**
- **Found during:** Task 1 — reviewing App.tsx session bootstrap logic
- **Issue:** The bootstrap redirected any unbound-device path to /select, which would prevent members from accessing /redeem/:code on a device not paired to a profile
- **Fix:** Added `/redeem` to the exemption list alongside `/pair` in the session bootstrap effect
- **Files modified:** frontend/src/App.tsx
- **Commit:** c321985

**2. [Rule 3 - Blocking Issue] node_modules symlink for worktree lint/typecheck**
- **Found during:** Task 1 verification — tsc and eslint could not resolve modules
- **Issue:** The worktree's frontend/ directory had no node_modules; lint and typecheck could not run
- **Fix:** Created a symlink `worktree/frontend/node_modules → main/frontend/node_modules`
- **Impact:** Enables lint/typecheck in worktree without installing packages; symlink lives only in the worktree and will not be committed (node_modules is gitignored)
- **Commit:** n/a (symlink not committed — gitignored)

**3. [Rule 2 - Missing Critical Functionality] Copied gruvax-logo-icon.svg to frontend/public/**
- **Found during:** Task 1 — RedeemPage references `/gruvax-logo-icon.svg` as a static asset
- **Issue:** The SVG existed in `design/` but not in `frontend/public/` where Vite serves static files
- **Fix:** Copied the SVG to `frontend/public/gruvax-logo-icon.svg`
- **Files modified:** frontend/public/gruvax-logo-icon.svg (created)
- **Commit:** c321985

### ESLint react-hooks/set-state-in-effect Handling

The ESLint rule flags `setState` calls in synchronous effect bodies. Two cases required disables:
- `RedeemPage.tsx`: `setPageState('invalid')` in the early-return guard when `!code`
- `ProfileDrawer.tsx`: `setTtlSeconds(null)` in the early-return guard when `!inviteInfo`

Both are legitimate (syncing with external URL params / derived state), matching the existing pattern in `KioskView.tsx`. Async callbacks (`.then()`, `setInterval` tick) are exempt from the rule and need no disable.

## Security Notes

| Threat ID | Mitigation Status |
|-----------|------------------|
| T-07-13 | PAT in type=password + autocomplete=off; never written to localStorage/sessionStorage/URL; only in component state and POST body |
| T-07-14 | ProfileDrawer INVITE LINK section shows only the URL and TTL countdown; no PAT field or value anywhere in the owner flow |
| T-07-15 | Accepted — backend returns uniform 404 regardless; frontend shows generic "not valid" copy for all negative cases |
| T-07-16 | collection_changed parse in try/catch; graceful degrade (no pill on failure); no es.close() inside the handler |

## Known Stubs

None — all components wire to real Plan 01/02 backend endpoints.

## Threat Flags

No new threat surfaces beyond those in the plan's threat register. The frontend components consume existing endpoints (Plans 01/02) without opening any new API surface.

---
*Phase: 07-member-self-connect-collection-diff*
*Completed: 2026-06-01 (all 3 tasks; human-verify checkpoint approved)*

## Self-Check: PASSED

### Files exist:
- frontend/src/api/inviteClient.ts: FOUND
- frontend/src/routes/redeem/RedeemPage.tsx: FOUND
- frontend/src/routes/redeem/RedeemPage.css: FOUND
- frontend/public/gruvax-logo-icon.svg: FOUND
- frontend/src/api/types.ts: FOUND (modified)
- frontend/src/api/adminClient.ts: FOUND (modified)
- frontend/src/App.tsx: FOUND (modified)
- frontend/src/routes/admin/ProfileDrawer.tsx: FOUND (modified)
- frontend/src/routes/admin/ProfileDiagnosticsCard.tsx: FOUND (modified)
- frontend/src/routes/kiosk/KioskView.tsx: FOUND (modified)
- frontend/src/routes/kiosk/kiosk.css: FOUND (modified)

### Commits exist:
- c321985: feat(07-03): types + invite client + public redeem page (AUTH-02 member UI)
- 64d8e6c: feat(07-03): owner invite affordance + admin diagnostics row + kiosk new-records pill

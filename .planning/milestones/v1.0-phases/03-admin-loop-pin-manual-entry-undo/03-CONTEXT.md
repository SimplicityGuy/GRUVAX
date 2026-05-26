# Phase 3: Admin Loop (PIN + Manual Entry + Undo) - Context

**Gathered:** 2026-05-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Boundaries stop being a committed fixture and become a **maintained artifact**. The owner
signs in (mobile-first; kiosk fallback works without a system keyboard), hand-edits a cube's
`(first_label, first_catalog) / (last_label, last_catalog)` with collection-fed autocomplete,
sees a diff preview (with downstream record-movement impact) before commit, every change is
logged by change-set with one-tap revert, and the **kiosk** gains two reveal features
(per-cube fill level + tap-to-see-contents) backed by the now-editable boundary data.

**In scope (10 requirements):** ADMN-01, ADMN-02, ADMN-03, ADMN-06, ADMN-07, ADMN-08,
ADMN-09, ADMN-12, CUBE-07, CUBE-09.

Concretely, Phase 3 delivers:
- **PIN auth** (4-digit, Argon2id in `gruvax.settings`) with server-side session rows, signed
  HttpOnly cookie + CSRF double-submit, sliding 10-min idle TTL + 60s countdown, manual logout,
  a Lock button, a hard session cap, failed-attempt lockout, and Change-PIN.
- A **bootstrap CLI** (`gruvax set-pin`) that provisions/rotates the PIN hash into the DB.
- An **`/admin/cubes` grid overview** (read-only, fill levels) + a **per-cube editor** with
  two-step dependent autocomplete, phantom-blocking validation (trigram near-misses + explicit
  override), and an inline index-space **midpoint suggestion**.
- A **diff preview** (mini-grid + before/after values + record-movement counts) gating every
  commit; mutations write `gruvax.boundary_history` grouped by `change_set_id`.
- **Undo by change-set** (inverse change-set, conflict-aware), via a History view.
- **Kiosk reveal:** per-cube **fill level** (CUBE-07) and **tap-to-reveal cube contents**
  (CUBE-09) via `GET /api/cubes/{unit}/{row}/{col}` — public on the kiosk.

**Out of scope (later phases):** SSE cross-device live refresh + `admin_editing` soft-lock (P4);
recently-pulled / privacy floors (P4); LED color/brightness/diagnostic settings + panic-off (P5);
CSV/YAML import + guided reshuffle wizard (P6); boundaries.yaml export (P6); Pi kiosk runtime
hardening (P7). Per-visitor PIN remains out of scope (v2).

</domain>

<decisions>
## Implementation Decisions

### Admin Access & Session (ADMN-01, ADMN-02, ADMN-08)
- **D-01:** PIN is **4-digit numeric**, Argon2id-hashed (`passlib[argon2]`) in
  `gruvax.settings` under key `auth.pin_hash`. Numeric-only keeps the kiosk fallback a 10-key
  keypad (Pitfall 4). The PIN is **never logged**, even at DEBUG (Pitfall 12). Verification uses
  `secrets.compare_digest` on the hash path.
- **D-02:** The **first PIN is provisioned via a bootstrap CLI** (`gruvax set-pin`) that
  Argon2id-hashes the PIN into `gruvax.settings.auth.pin_hash`. **This resolves the project's
  long-carried open question** ("PIN hash location — env var or `gruvax.settings`?"): it lives in
  the DB, set by CLI. Plaintext never touches `.env` or git; re-runnable to rotate from the server.
- **D-03:** **All four safety affordances ship in this phase** (all small, all research-recommended):
  (a) **failed-attempt lockout** / login rate-limit — important given the 4-digit PIN's ~10k
  combinations; (b) **Change PIN** in Settings (requires current PIN, writes new hash, revokes all
  other sessions — Pitfall 12); (c) **Lock button** (re-shows PIN without ending the session —
  Pitfall 23); (d) **hard session cap** (force re-PIN after a max lifetime regardless of activity —
  Pitfall 23).
- **D-04:** Session is a **10-minute idle sliding window** with a **visible 60-second countdown**
  before logout (ADMN-02). **Uncommitted edits are preserved client-side** (Zustand
  `pendingChangeSet`), so a timeout never loses in-progress work — re-enter the PIN and the pending
  diff is still there to commit; nothing reaches the DB until commit anyway. **Manual logout from
  any screen** (ADMN-08). Auth state = server-side `gruvax.admin_sessions` rows + signed HttpOnly
  session cookie + CSRF double-submit cookie (`SameSite=Strict`, Pitfall 13); the SPA's
  `isLoggedIn` is a mirror, learned via `GET /api/admin/session`.

### Boundary Editing Model (ADMN-03, ADMN-06, ADMN-12)
- **D-05:** **`/admin/cubes` grid overview** (read-only, shows each cube's fill level) +
  a focused **per-cube editor** (`/admin/cubes/:unit/:row/:col`) for first/last `(label, catalog#)`.
  Bulk reshuffle stays in the **Phase 6 wizard** — not here.
- **D-06:** **Two-step dependent autocomplete**: pick the **label first** (distinct labels in
  `v_collection`), then the **catalog#** autocompletes scoped to that label's records. Source is
  **exclusively `gruvax.v_collection`** (Pitfall 5). Mirrors the shelf's label→catalog ordering and
  makes phantom pairs rare by construction.
- **D-07:** **Phantom handling** (a value with no `v_collection` match — e.g., a sold record,
  Pitfall 6): **block the save, surface the closest trigram near-misses as tappable suggestions,
  and allow "use anyway" only behind an explicit confirm.** One flow satisfies ADMN-03 ("no
  free-text unless explicitly confirmed") **and** ADMN-06 (trigram near-misses) **and** the legit
  sold-record-as-boundary edge. Save validation runs through the **POS-01 normalizer/comparator**
  (`normalize.py`) — no raw-string compares (carry-forward D-13); rejects `first > last`.
- **D-08:** **"Suggest midpoint" (ADMN-12)** is an **inline button** in the per-cube editor,
  **always available** when the cube sits between two adjacent populated cubes. It walks the
  **collection-INDEX space, never catalog-string space** (Pitfall 22) — the suggestion is always a
  real record. **Editable, never auto-applied.**

### Diff Preview & Undo (ADMN-07, ADMN-09)
- **D-09:** The **pre-commit diff preview** shows affected cubes highlighted on a **mini Kallax
  grid** + a **per-cube before→after** list of changed boundary values + **record-movement counts**
  ("12 records now fall in B2 instead of B1"; "B3 becomes empty"), computed from the **in-memory
  collection snapshot** (Phase 2) — catches emptied/overstuffed-cube mistakes before commit. No DB hit.
- **D-10:** Mutations write **`gruvax.boundary_history` grouped by `change_set_id`** (append-only).
  One save action = one change-set (a manual single-cube edit is a 1-cube change-set). Multi-cube
  edits accumulate in `pendingChangeSet` client-side, then a **single atomic** `POST /api/admin/cubes/bulk`
  (Pitfall 11). Mutating POSTs carry an **`Idempotency-Key`** (ARCHITECTURE).
- **D-11:** **Revert granularity = whole change-set only** (matches ADMN-09). Revert restores each
  cube's prior value as a **new inverse change-set** (`source='revert'`), so the revert is **itself
  undoable**.
- **D-12:** **Revert conflict handling:** when reverting an older change-set whose cubes were
  modified by a **newer** change-set, **revert the non-conflicting cubes and SKIP + REPORT** the
  conflicting ones ("B2 changed since this edit — not reverted"). No silent clobber; the inverse
  change-set records exactly which cubes it touched.

### Kiosk Reveal Features (CUBE-07, CUBE-09)
- **D-13:** **Fill level** (CUBE-07) = records-in-range ÷ **nominal cube capacity** (a Kallax cube
  holds ~90–100 LPs; **capacity is an admin Settings value**). Reads as a true fullness gauge and
  flags overstuffed cubes; computed from the in-memory snapshot. Pairs with the D-09 movement counts.
- **D-14:** **Cube tap** (CUBE-09) → reverse-lookup side panel via **`GET /api/cubes/{unit}/{row}/{col}`**:
  the cube's **first & last** boundary records + **~6–8 records evenly sampled** across the range +
  a **total count** ("94 records in this cube"). Source `v_collection`.
- **D-15:** Reveal features (fill level + cube contents) are **PUBLIC on the kiosk** — visiting
  friends can browse; nothing sensitive (the collection is already searchable); LAN-only. Matches
  PROJECT's "visiting friends" use case.
- **D-16:** Tapping an **unset/empty cube** shows a plain-language "No records assigned to this cube
  yet" panel; **if an admin is logged in**, that panel offers a **one-tap shortcut** into that cube's
  editor.

### Kiosk Admin Input & Settings Scope
- **D-17:** Kiosk boundary editing uses **tap-to-pick lists, not typing** — a **label list with an
  A–Z jump rail** → **catalog#s scoped to the chosen label**; the **numeric keypad** enters the PIN
  and digit-filters catalog#s. **No in-app letter board is built** (sidesteps labwc/squeekboard
  #2926 entirely); phantoms are impossible by construction on the kiosk. Mobile reuses the same
  components with the device's real keyboard for faster type-to-filter. Satisfies ROADMAP
  criterion 1 (boundary editor reachable on the kiosk).
- **D-18:** The **Phase 3 Settings page contains only**: Change PIN + cube **nominal-capacity** +
  **idle-timeout** duration. **LED color/brightness settings are deferred to the Phase 5 LED
  milestone** — don't build UI for features that don't exist yet.

### Claude's Discretion (delegated to researcher / planner / ui-phase)
- Exact **lockout policy** numbers (attempt threshold, cooldown window), **hard-cap** duration
  (ARCHITECTURE/Pitfall 23 suggest ~30 min), and the idle default (10 min within the 5–10 min range).
- **Cookie/CSRF specifics** (HttpOnly, `Secure`, `SameSite`, session-token entropy) per ARCHITECTURE
  "Where does PIN auth state live" + Pitfall 13 — implement to that spec.
- **Trigram near-miss query + similarity threshold** for boundary validation — reuse the Phase 2
  `pg_trgm` did-you-mean path; tune against the real CSV.
- **Nominal cube capacity default** (~90–100) and how fill-level intensity maps onto design tokens.
- **Evenly-sampled subset size** (~6–8) and the sampling method (index-stride).
- **New Alembic migration** for `boundary_history`, `admin_sessions`, `settings`, `idempotency_keys`
  per ARCHITECTURE DDL — follow Phase 1 conventions (`alembic_version` in `public` schema; `search_path`
  via connect event listener).
- **All visual/interaction design** (admin chrome, keypad, A–Z rail, tap-to-pick lists, mini-grid
  diff, side panel, fill-level rendering, countdown) → **`/gsd-ui-phase 3`** within the Nordic Grid
  design system.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Admin Architecture & Contracts (authoritative for this phase)
- `.planning/research/ARCHITECTURE.md` — the **`/api/admin/*` endpoint surface**
  (login/logout/session, cubes GET/PUT, `cubes/bulk`, `cubes/validate` dry-run diff,
  `cubes/suggest` midpoint, `history` + `history/{id}/revert`, `settings`), the **`gruvax.boundary_history`
  / `admin_sessions` / `settings` / `idempotency_keys` DDL**, the **auth model** (signed HttpOnly
  cookie + CSRF double-submit, server-side session rows), the **`/admin/*` route tree**, the
  **`GET /api/cubes/{unit}/{row}/{col}` reverse-lookup**, and the Zustand `admin` store slice.
- `.planning/research/PITFALLS.md` — **Pitfall 4** (kiosk keyboard #2926 → keypad / tap-to-pick),
  **Pitfall 5** (`v_collection` only contact surface), **Pitfall 6** (phantom boundary records),
  **Pitfall 11** (partial change-set → `pendingChangeSet` + atomic bulk), **Pitfall 12** (PIN
  rotation / Change-PIN / never log), **Pitfall 13** (CSRF / `SameSite=Strict`), **Pitfall 22**
  (midpoint in index space, not catalog-string space), **Pitfall 23** (idle timer + hard cap + Lock).
- `.planning/research/INTERPOLATION.md` — §6 edge cases for the save-validator comparator; the
  index-space walk underpinning the midpoint suggestion.
- `.planning/research/STACK.md` — `passlib[argon2]` for the PIN hash, Starlette `SessionMiddleware`
  + `itsdangerous`, psycopg async, Alembic.
- `.planning/research/FEATURES.md` — Category 2/3 differentiators (cube-contents reveal, diff
  preview, auto-suggest midpoint) for intent/feel.

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` — definitions for ADMN-01/02/03/06/07/08/09/12, CUBE-07/09.
- `.planning/ROADMAP.md` — Phase 3 section: goal + 5 success criteria.
- `.planning/PROJECT.md` — single-PIN/session-timeout constraint, "visiting friends" use case,
  repo-hygiene rule (CSV + `background/` never committed).

### Locked from Prior Phases (carry forward — do not re-decide)
- `.planning/phases/01-first-search-cube-highlight/01-CONTEXT.md` — **D-03** (real `units` /
  `cube_boundaries` tables; admin writes the **same** tables), **D-07** (`v_collection` is the only
  read surface + startup probe), **D-13** (POS-01 normalizer is the only legal comparison path;
  raw-string compares forbidden).
- `.planning/phases/02-real-position-estimation/02-CONTEXT.md` — the **in-memory collection snapshot**
  (reused for fill-level, record-movement counts, cube-contents) and the **SRCH-07 `pg_trgm`** path
  (reused for boundary near-miss suggestions).
- `src/gruvax/estimator/normalize.py` — POS-01 normalizer + `catalog_in_range`; the save validator,
  midpoint, and fill-level range checks must use this.
- `src/gruvax/estimator/collection_snapshot.py` — per-label record lists; fill counts, movement diff,
  and cube-contents subset all read from it.
- `src/gruvax/estimator/boundary_cache.py` — admin commits must `invalidate()`/reload it in-process
  (SSE wiring is Phase 4).
- `src/gruvax/db/queries.py` — psycopg `%s` placeholder convention; zero f-string SQL (Phase 2);
  add admin queries here. `src/gruvax/db/pool.py` — async pool, per-request connections.
- `src/gruvax/api/deps.py` — dependency-provider pattern (`get_pool`, `get_boundary_cache`); add
  `require_admin` / session deps. Routers imported inside `create_app()` (Phase 1 circular-import fix).
- `src/gruvax/settings.py` — pydantic-settings config (PIN is DB-seeded, so no new PIN env var).
- `migrations/` — Alembic conventions (versions 0001–0003; `alembic_version` in `public`, `search_path`
  via connect listener); add `0004` for the admin tables.
- `frontend/src/routes/kiosk/ShelfGrid.tsx` / `Cube.tsx` / `gridGeometry.ts` — reused for the admin
  mini-grid diff, the `/admin/cubes` grid, and fill-level rendering (row/unit-wrap mapping).
- `frontend/src/api/client.ts` (TanStack Query imperative) and `frontend/src/state/store.ts` (Zustand) —
  add admin query keys + an `admin` slice (`isLoggedIn` mirror, `sessionExpiresAt`, `pendingChangeSet`).

### Design System (consume tokens; never hardcode hex)
- `design/gruvax-design-language.md` — Nordic Grid; cell states; **never recolor a lit cell**;
  LED-physics motion; ALL-CAPS labels (Barlow Condensed); DM Mono for catalog#s/counts.
- `design/gruvax-design-tokens.css`, `design/gruvax-design-tokens.json` — token contract.
- `CLAUDE.md` — conventions, Mermaid-only diagrams.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`collection_snapshot.py`** — fill-level counts, record-movement diff, and cube-contents subset
  all derive from the in-memory per-label record lists (no DB during compute).
- **`normalize.py` (POS-01)** — the save validator's comparison path, midpoint index walk, and
  range-membership tests; raw-string compares forbidden (carry-forward D-13).
- **`boundary_cache.py`** — `invalidate()`/reload after every admin commit (in-process in Phase 3).
- **Phase 2 `pg_trgm` did-you-mean** (`api/search.py` + migration `0003`) — reused for the boundary
  near-miss suggestions in D-07.
- **`ShelfGrid` / `Cube` / `gridGeometry.ts`** — reused for the admin grid view, the mini-grid diff
  preview, and fill-level rendering.

### Established Patterns
- **CPU-only reads from the in-memory snapshot, no DB during compute** (Phase 1/2).
- **Dependency providers in `deps.py`; routers imported inside `create_app()`** (circular-import fix).
- **psycopg `%s` placeholders, parameterized SQL, zero f-string interpolation** (Phase 2 security).
- **`alembic_version` in `public` schema; `search_path` via connect event listener** (Phase 1).
- **Float confidence + token-only CSS / design tokens** (no hardcoded hex).

### Integration Points
- New `gruvax` schema tables: `boundary_history`, `admin_sessions`, `settings`, `idempotency_keys`.
- New endpoints: `/api/admin/*` (session-gated, CSRF) + **public** `GET /api/cubes/{unit}/{row}/{col}`.
- Admin writes `units` / `cube_boundaries` (same tables the boundary cache loads) → **invalidate the
  cache in-process** on commit (cross-device live refresh via SSE is Phase 4).
- New frontend `/admin/*` route tree (mobile-first responsive; kiosk fallback = same components).

</code_context>

<specifics>
## Specific Ideas

- The ARCHITECTURE.md **DDL** for `boundary_history` (`change_set_id UUID`, append-only,
  `changed_at DESC` index), `admin_sessions` (server-side token rows, `expires_at`), and `settings`
  (key/value: `auth.pin_hash`, cube capacity, idle TTL) are concrete copy-from references.
- The ARCHITECTURE.md **admin endpoint table** is the intended surface for this phase — minus the
  LED/color/diagnostics/export rows (those are Phases 5/6).
- Kiosk numeric **keypad ≈ 10-key**, tap-targets ≥ 44pt (Pitfall 4). Label picker uses an **A–Z jump
  rail**; catalog picker is digit-filtered.
- **Midpoint = index-space walk** of `v_collection` between two adjacent cubes' boundary records
  (Pitfall 22 remedy) — the suggestion is always a real, owned record.

</specifics>

<deferred>
## Deferred Ideas

- **SSE cross-device live admin refresh + `admin_editing` soft-lock** → **Phase 4**. ⚠ **Known
  limitation this phase:** with no SSE yet, an admin editing on the phone won't live-update the
  kiosk grid — the kiosk reflects changes on next load; admin commits invalidate the cache in-process
  only.
- **CSV/YAML import + guided reshuffle wizard** → Phase 6.
- **`GET /api/admin/export/boundaries.yaml`** → Phase 6 (import/export).
- **LED color/brightness/diagnostic settings + panic-off** → Phase 5.
- **Recently-pulled / privacy floors** → Phase 4.
- **Per-visitor PIN** (project open question) → v2 (out of scope).
- **Owner-curated real golden positions** (closes Phase 2's D-08 softening) — this phase's admin
  tooling *enables* a real reshuffle, but running the validation harness against real boundaries is
  Phase 6 / post-reshuffle.
- **Per-cube partial revert** (vs whole change-set) — considered; deferred (whole change-set chosen, D-11).

</deferred>

---

*Phase: 03-admin-loop-pin-manual-entry-undo*
*Context gathered: 2026-05-20*

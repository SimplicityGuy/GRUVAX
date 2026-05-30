# Phase 1: Walking skeleton — API client + single-profile sync - Context

**Gathered:** 2026-05-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Restore the Core Value loop (typed query → cube highlight ≤ 200 ms) end-to-end against API-sourced collection data, with `gruvax.v_collection` and its read-only grant retired. Positioning runs off a new local `gruvax.profile_collection` cache populated from `discogsography GET /api/user/collection` via a paged + retrying httpx client, scoped to a single default profile (deterministic UUID `00000000-0000-0000-0000-000000000001`).

**In scope (P1):**
- New tables: `profiles` (full schema), `profile_collection`.
- Nullable `profile_id` added to 7 v1 tables, backfilled to the default profile.
- `DiscogsographyClient` (httpx, offset/limit paging, 401/403/429/5xx retry semantics).
- `sync_profile(profile_id)` routine using staging-swap with per-profile advisory lock; refresh in-process caches inline at end.
- `gruvax-set-pat` CLI (stdin only; inline `limit=1` test sync; strict user_id match) and `gruvax-sync` CLI (calls a new PIN-gated `POST /api/admin/profiles/{id}/sync` endpoint that runs sync in-process).
- Drop `gruvax.v_collection` view + revoke read-only grant + drop `OBSERVED_DISCOGSOGRAPHY_SCHEMA` setting + simplify search_path to `gruvax, public` — all in the same Alembic migration.
- `/api/health` field renamed `discogsography_view_check` → `discogsography_api_check`, derived from last-sync state (`ok | failed | stale`).
- Fake-discogsography FastAPI fixture for tests + dev (sibling Compose service); CI SLO gate seeds `profile_collection` via SQL fixtures directly.
- `DISCOGSOGRAPHY_BASE_URL` env var validated at boot.
- Migration is fully round-trippable (downgrade re-creates view + grant + drops new tables/columns).

**Out of scope (handled by P2–P4):**
- The 6 other profiles + admin profile manager UI + the `profile_id NOT NULL` migration (P2).
- Per-profile SSE channel + browser session profile picker + multi-profile cache routing (P2).
- Devices + pairing codes + fingerprint cookie + RPi pairing UX (P3).
- Nightly background sync scheduler, 401 reauth UI, per-profile diagnostics cards, soft-delete cache-purge task, "Sync now" progress toast (P4).

</domain>

<decisions>
## Implementation Decisions

### Schema split — `profiles` + PAT storage
- **D-01:** **Full `profiles` schema lands in P1.** Alembic migration creates the table per refined spec — `id UUID PK DEFAULT gen_random_uuid()`, `display_name TEXT NOT NULL`, `discogs_username TEXT`, `discogsography_user_id UUID`, `app_token_encrypted BYTEA NOT NULL` (Fernet-encrypted via `GRUVAX_SECRET_KEY`), `app_token_revoked BOOLEAN NOT NULL DEFAULT FALSE`, `created_at`, `last_sync_at`, `last_sync_status`, `last_sync_error`, `last_sync_item_count`, `deleted_at`. Partial-unique indexes on `LOWER(display_name) WHERE deleted_at IS NULL` and on `discogsography_user_id WHERE deleted_at IS NULL`. **Rationale:** P2 only has to add the FK fanout migration across the 7 v1 tables + the admin UI; no second `profiles` schema migration; `GRUVAX_SECRET_KEY` + Fernet wiring lands once. Boot fails if `GRUVAX_SECRET_KEY` is missing (mirrors v1's `DATABASE_URL` / `SESSION_SECRET` pattern).

- **D-02:** **Seed the default profile in the migration.** Row inserted with `id = '00000000-0000-0000-0000-000000000001'`, `display_name = 'Default'` (renameable in the P2 admin UI), `app_token_encrypted = Fernet('') of an empty placeholder` (concrete: the migration inserts a row with `app_token_encrypted` set to a Fernet-encrypted empty string — overwritten on first `gruvax-set-pat`). `app_token_revoked = TRUE` until first successful test-sync.

### Schema — `profile_collection` PK
- **D-03:** **PK = `(profile_id, release_id, folder_id)`.** Resolves the contract drift: discogsography's `releases[]` items have no `instance_id`. Treating `(release_id, folder_id)` as the natural key preserves the "main vs wantlist-archive folder" duplicate case (matches the sketch-finding "counts come from row-counting, dupes + variants surface on purpose"). Two distinct rows for the same release in the same folder are not modeled — Discogs surfaces those as `quantity`, not separate items; acceptable loss.
- **D-04:** `release_id` is stored as `BIGINT` even though the contract serializes it as a string (`"id": "12345"`). Client parses on ingest. Other columns mirror the contract envelope: `instance_id` is **removed from the schema** (not in the contract); add `folder_id INT` instead. Final shape: `(profile_id UUID, release_id BIGINT, folder_id INT, artist TEXT, title TEXT, label TEXT, catalog_number TEXT, year INT, fts_vector TSVECTOR GENERATED ALWAYS AS (weighted: A=catalog, B=title, C=artist || ' ' || label) STORED, synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW())`. Indexes per spec — GIN on `fts_vector`, `(profile_id, label, catalog_number)`, GIN trigram on artist + title.

### Sync state machine
- **D-05:** `last_sync_status ∈ {'ok', 'failed', 'in_progress'}` (3 values, no `'pat_rejected'` 4th). PAT rejection surfaces via the `app_token_revoked BOOLEAN` flag, which flips true on any 401/403 (`PATRejected`). The flag is the queryable signal the P4 reauth-required badge will read.
- **D-06:** `last_sync_error` carries a short tag string ∈ `{'pat_rejected', 'network', 'rate_limited', 'server_error', 'cancelled', NULL}`. Not JSONB.

### `gruvax-set-pat` CLI
- **D-07:** **Input: stdin only.** Either `echo $PAT | gruvax-set-pat --profile default` or run interactively and paste at the prompt. No `--pat` flag; no env var fallback inside the CLI. Avoids shell history / `ps` / journald leakage.
- **D-08:** **Inline test-sync, then exit.** CLI synchronously hits `GET /api/user/collection?limit=1` against `DISCOGSOGRAPHY_BASE_URL`, captures `user_id` from the response envelope, and validates `catalog_number` is present on the sample item. On success: writes the Fernet-encrypted PAT to `profiles.app_token_encrypted`, sets `discogsography_user_id` to the captured value, flips `app_token_revoked = FALSE`. On failure: exits non-zero, leaves the existing row untouched.
- **D-09:** **Rerun semantics (rotation): strict.** A second invocation must (a) succeed against the test-sync AND (b) yield a `user_id` equal to the existing `discogsography_user_id` on the row. A mismatched user_id exits non-zero with the message: `"PAT belongs to a different discogsography user (was <old>, got <new>). Soft-delete the profile first if you really intend to switch."`. Preserves the "one discogsography user ↔ one profile" invariant before it becomes load-bearing in P2.

### Full-sync trigger in P1
- **D-10:** **Separate `gruvax-sync` CLI; calls the API over HTTP.** `gruvax-set-pat` only does the test-sync. The owner runs `gruvax-sync --profile default` to trigger the full sync. The CLI POSTs to a new endpoint `POST /api/admin/profiles/{profile_id}/sync` (PIN-gated by the existing v1 `require_admin` dependency); the sync runs inside the API process; the CLI streams progress lines to stdout until completion. Reuses one code path that P4's "Sync now" admin button will also hit. CLI prompts for the admin PIN once per invocation (read from stdin, sent in the request header used by v1 admin flows).

### `profile_id` migration timing across v1 tables
- **D-11:** **Add nullable `profile_id` to all 7 v1 tables in P1, NOT NULL in P2.** Tables: `cube_boundaries`, `segments`, `change_log`, `change_sets`, `settings`, `record_stats`, `ambient_baseline`. P1 migration adds `profile_id UUID NULL REFERENCES profiles(id) ON DELETE CASCADE` and backfills existing rows with the default UUID. All P1 query call sites pass `profile_id` (the value is constant — only one profile exists — but the signature is in place). P2 just tightens to `NOT NULL` and adds composite uniqueness indexes. Spreads the migration risk; P2 is a pure schema change with no query-rewrite work.

### `OBSERVED_DISCOGSOGRAPHY_SCHEMA` cleanup
- **D-12:** **Rip out the setting in P1.** Remove `OBSERVED_DISCOGSOGRAPHY_SCHEMA` from `settings.py`. Simplify `db/pool.py::_configure_connection` to set `search_path = gruvax, public` (drops the dev/prod schema branch entirely). One-time cleanup that matches the spirit of D7 (decouple GRUVAX from discogsography's DB).

### `/api/health` transition
- **D-13:** **Rename `discogsography_view_check` → `discogsography_api_check`, derived from last-sync state.** Field is `'ok' | 'failed' | 'stale'`:
  - `ok` = `last_sync_status = 'ok'` AND `app_token_revoked = FALSE`
  - `failed` = `last_sync_status = 'failed'` OR `app_token_revoked = TRUE`
  - `stale` = `last_sync_at IS NULL` OR `now() - last_sync_at > 24h`
  No per-request HTTP egress (matches v1's "no live DB probe on /api/health" philosophy). Overall `status` becomes `degraded` only when `db_ok = FALSE` OR `discogsography_api_check != 'ok'`. The existing `sync_age_seconds` 60s background refresh task is replaced by a single read of `profiles.last_sync_at` for the default profile.

### Cache refresh after sync
- **D-14:** **Inline at end of sync, in-process.** Because `gruvax-sync` calls the HTTP endpoint inside the API process, the sync routine itself calls `snapshot.invalidate()` + `snapshot.load(pool)` + `segment_cache.invalidate()` + `boundary_cache.reload()` after the staging-swap commits and before returning the HTTP response. Uses the same code paths today's lifespan startup uses; P2 replaces the inline call with an SSE publish that any process consumes.

### Dev/CI synthetic discogsography
- **D-15:** **Fake-discogsography FastAPI fixture.** New file `tests/fixtures/fake_discogsography.py` implementing the three contract endpoints (`/api/user/collection`, `/api/user/collection/stats`, `/api/user/collection/timeline`) backed by an in-memory store. Supports token routing (`dscg_` prefix), scope check, 401/403/429/5xx triggers via query params or magic tokens. Used by `DiscogsographyClient` unit tests (retry semantics, pagination, error mapping) running against an in-process httpx `AsyncClient(transport=ASGITransport(app=fake_app))`.
- **D-16:** **Compose has a `fake-discogsography` sibling service.** On `docker compose up`, the fake serves the contract endpoints with its in-memory store seeded from a YAML/JSON fixture (~3000 synthetic rows). An init-sync container runs `gruvax-sync default` against it on first start (idempotent — skips if `profile_collection` is already populated for the default profile). Dev sees a real full sync end-to-end on every clean boot. Trade-off: dev `up` is slower; matches real flow.
- **D-17:** **SLO/integration tests bypass the sync path** — they seed `profile_collection` directly via SQL fixtures (e.g. `tests/fixtures/synth_profile_collection.sql`) since they're exercising positioning, not sync. The existing v1.0 `tests/fixtures/synth_collection.sql` targeting `gruvax_dev.collection_items` is rewritten as `synth_profile_collection.sql` targeting `gruvax.profile_collection` for the default profile UUID.
- **D-18:** **`DISCOGSOGRAPHY_BASE_URL` env var, validated at boot.** Prod = `http://discogsography-api:8004`. Dev compose = `http://fake-discogsography:8004`. Tests = monkeypatched. No per-profile URL column; no settings-row indirection. Mirrors v1's `MQTT_HOST` / `DATABASE_URL` pattern.

### Alembic downgrade
- **D-19:** **Full round-trip.** Downgrade re-creates `gruvax.v_collection` with the original view body, re-issues the read-only grant to discogsography's role, drops `profiles` + `profile_collection`, drops the nullable `profile_id` columns from the 7 v1 tables. Preserves the v1.0 CI invariant (`upgrade head → downgrade base → upgrade head` round-trip clean) called out in the `integration_test_harness` memory.

### Claude's Discretion
- Exact admin PIN auth UX for `gruvax-sync` CLI (single prompt vs `getpass` vs read once and reuse for the run) — planner picks the simplest fit.
- The fake-discogsography fixture's in-memory store seed format (YAML vs JSON vs Python literal) — planner picks; the existing synth dataset shape (~3000 rows with label/catalog_number/artist/title) drives the schema.
- Exact log redaction strategy for the `Authorization` header (likely a structlog processor that masks any `Bearer dscg_*` value) — implementation choice, constraint is "PAT plaintext NEVER logged at any level."
- Whether `gruvax-sync` prints progress as plain log lines or a TTY progress bar — plain log lines preferred for Compose-exec ergonomics, but planner can pick.
- Exact mapping of `last_sync_error` values — set listed above is the contract; planner can extend it if a sync failure mode doesn't fit a tag.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Cross-repo contract (load first)
- `/Users/Robert/Code/public/discogsography/docs/specs/v2-gruvax-integration.md` — **discogsography v2 integration contract, v1 (stable 2026-05-26).** This is the authoritative source for endpoint shape, auth, rate limits, and the OpenAPI fragment. P1 client + tests must conform to this. Note: lives in the **discogsography repo**, not GRUVAX.

### GRUVAX-side specs (load second)
- `docs/superpowers/specs/2026-05-26-v2-multi-user-collections-refined.md` — Refined design spec; **§Data Model**, **§API Client + Sync**, **§Phase Decomposition → P1**, **§Constraints → New in v2.0** are the load-bearing sections for P1. Decisions D-03 (PK), D-13 (health), D-15 (fake), D-19 (round-trip) override the spec's assumptions where contract drift required it.
- `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` — Original 2026-05-25 SPEC. Superseded by the 2026-05-26 refined version for any contradiction; kept as reference for the spec's "Locked Decisions" framing (D1–D7).
- `.planning/intel/SYNTHESIS.md` — Entry point for the ingested intel; pointers to decisions/constraints/requirements/context.
- `.planning/intel/decisions.md` — D1–D7 + D-meta locked at design time.
- `.planning/intel/constraints.md` — 11 constraints (schema, api-contract, protocol, nfr). CON-200ms-slo-preserved + CON-offline-resilience-preserved + CON-staleness-redefinition + CON-rate-limit-collection-api are the v1 invariants P1 must not regress.
- `.planning/intel/context.md` — Background narrative + risks. Risk #1 (catalog# exposure) is resolved by the contract artifact (P1 spike outcome: populated via `metadata` JSONB on the discogsography side).
- `.planning/intel/requirements.md` — 18 candidate reqs; P1 maps to API-01, API-02 (single-profile flavor), API-03, SYN-02 (single-profile flavor), PROF-03.

### Project context
- `.planning/PROJECT.md` — Current State + Current Milestone (v2.0).
- `.planning/REQUIREMENTS.md` — v2.0 active requirements + traceability table (P1 owns API-01, API-02, API-03, SYN-02, PROF-03).
- `.planning/ROADMAP.md` — v2.0 phase decomposition; **§Phase 1** has the success criteria the verifier will score against.
- `.planning/STATE.md` — Pending todos + roadmap evolution (DGS-PREREQ resolved as of this session).

### v1.0 archive (reference only — supersedes-on-v2-milestone)
- `.planning/milestones/v1.0-ROADMAP.md` — Full v1.0 phase archive; relevant for understanding what the existing code is doing.
- `.planning/milestones/v1.0-REQUIREMENTS.md` — v1.0 reqs (SPIDR-deferred items are NOT pulled into v2.0 P1).
- `.planning/milestones/v1.0-MILESTONE-AUDIT.md` — v1.0 close audit.

### Existing code that P1 modifies or replaces
- `src/gruvax/db/pool.py` — `_configure_connection` simplifies; `OBSERVED_DISCOGSOGRAPHY_SCHEMA` branch removed (D-12).
- `src/gruvax/settings.py` — Drop `OBSERVED_DISCOGSOGRAPHY_SCHEMA`; add `DISCOGSOGRAPHY_BASE_URL` (boot-fail-if-missing) and `GRUVAX_SECRET_KEY` (boot-fail-if-missing for Fernet).
- `src/gruvax/db/queries.py` — `search_collection`, `get_release_for_locate`, `get_sync_staleness_seconds`, `get_phantom_boundary_count` all rewire from `gruvax.v_collection` to `gruvax.profile_collection` (single profile UUID for P1).
- `src/gruvax/estimator/collection_snapshot.py` — `load()` query changes from `SELECT release_id, label, catalog_number FROM gruvax.v_collection` to `SELECT release_id, label, catalog_number FROM gruvax.profile_collection WHERE profile_id = :default_uuid`.
- `src/gruvax/app.py` — Lifespan startup probe changes from `SELECT 1 FROM gruvax.v_collection LIMIT 1` to a `profile_collection` row-count check + a discogsography reachability check (cached); `sync_age_seconds` background task replaced by a read of `profiles.last_sync_at`.
- `src/gruvax/api/health.py` — Field rename (D-13).
- `migrations/versions/` — New migration appended; round-trip required (D-19).

### Sketch / spike findings
- `.claude/skills/sketch-findings-gruvax/SKILL.md` — Segment-aware boundary-editing visual decisions. Relevant invariant: "counts come from row-counting `v_collection` (dupes + variants), never catalog arithmetic — the record picker surfaces duplicate/variant rows on purpose." After P1 the source is `profile_collection`; the row-counting semantics carry over with composite-key resolution per D-03.

### Codebase intel
- `.planning/codebase/CONVENTIONS.md` — Nordic Grid design language + documentation conventions (Mermaid diagrams, README banner pattern).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **psycopg async pool + lifespan management** (`src/gruvax/db/pool.py`, `src/gruvax/app.py`) — P1 reuses verbatim; only the `_configure_connection` body simplifies. The pool already speaks to the shared Postgres.
- **Pydantic-settings boot validation pattern** (`src/gruvax/settings.py`) — `SESSION_SECRET` already follows the "no default → boot-fail-if-missing" convention. `GRUVAX_SECRET_KEY` and `DISCOGSOGRAPHY_BASE_URL` extend the same pattern.
- **CollectionSnapshot + invalidate() hook** (`src/gruvax/estimator/collection_snapshot.py`) — Phase 4 wired the SSE-refresh seam; P1 reuses it by calling `invalidate()` + `load()` inline at end of sync (D-14). P2 replaces the inline call with an SSE publish.
- **Admin PIN auth dependency** (`src/gruvax/auth/`) — Reused by the new `POST /api/admin/profiles/{id}/sync` endpoint.
- **CLI scaffold pattern** (`src/gruvax/cli/set_pin.py`) — Same pattern for `gruvax-set-pat` + `gruvax-sync` (entry_points in pyproject, async main, settings load).
- **SQL queries with `%s` parameterization** (`src/gruvax/db/queries.py`) — All P1 query rewires follow the same convention; SQLi protection invariant preserved.
- **Alembic migration template** (`migrations/versions/0001_create_schema.py` through `0008_record_stats.py`) — 8 prior migrations show the project's conventions (naming, op order, downgrade fidelity).
- **psycopg `Row Factory` → Pydantic** pattern (already used in `db/queries.py`).

### Established Patterns
- **One env var per integration target** — `DATABASE_URL`, `MQTT_HOST/PORT/USERNAME/PASSWORD`, soon `DISCOGSOGRAPHY_BASE_URL`. No client-discovery magic.
- **No live probes on `/api/health`** — All subsystem fields are derived from cached app-state set at lifespan startup or by background tasks. P1's `discogsography_api_check` field preserves this (D-13).
- **Alembic upgrade↔downgrade round-trip enforced in CI** — v1.0 CI invariant. P1 honors it (D-19).
- **Search uses parameterized `%s`; no f-string SQL interpolation** — T-01-07 SQLi protection. P1 queries follow same rule.
- **`gruvax.v_collection` is the ONLY contact surface with discogsography** — DEP-02 invariant. P1 retires the view + grant and replaces the contact surface with the HTTP API. After P1, **no code path in GRUVAX reads from discogsography's tables**.
- **Pitfall C (D-13 in v1.0 estimator)** — labels are casefolded, never normalize_catalog'd. Preserved post-rewire.

### Integration Points
- **`profile_collection` table is the new sole source of truth** for collection rows. Every v1 read against `v_collection` rewires to `profile_collection WHERE profile_id = <default_uuid>`.
- **`profiles.last_sync_at` replaces `max(v_collection.synced_at)`** for the staleness signal everywhere (kiosk banner, `/api/health`, `/admin/diagnostics` v1 surface).
- **New endpoint `POST /api/admin/profiles/{id}/sync`** — PIN-gated; same auth dependency as v1 admin endpoints; calls `sync_profile(profile_id)`; refreshes caches inline.
- **`fake-discogsography` Compose service** — sibling to `gruvax-api`; init-sync container runs once on `up`.
- **`DiscogsographyClient`** — new module `src/gruvax/discogsography/client.py` (or similar); httpx async; retry per spec.
- **`sync_profile(profile_id)`** — new module `src/gruvax/sync/` (or similar); the function called by both the HTTP endpoint and the (separate) CLI entry.

</code_context>

<specifics>
## Specific Ideas

- **Contract drift cheat-sheet for the planner (override the refined spec where listed):**
  - Pagination: `limit=N&offset=M` (max 200, default 50) — **not** `page=N&per_page=200`.
  - Envelope: `{user_id, releases, total, offset, limit, has_more}` — field is `releases`, not `items`; `user_id` is top-level; `has_more` is the termination signal.
  - Items: `id` (string, parse to BIGINT), `title`, `year`, `catalog_number` (nullable), `artist`, `label` (nullable), `genres`, `styles`, `rating`, `date_added`, `folder_id`. **No `instance_id`.**
  - Auth: `Authorization: Bearer dscg_<base64url-32-bytes>` (~50 chars total). Routed by prefix on discogsography side.
  - Errors: 401 (missing/invalid/revoked/wrong-prefix — all same body shape), 403 (missing scope), 429 (`Retry-After` + `X-RateLimit-*`), 5xx.
  - Rate limits: 60/min + 600/hour per token. Full sync at `limit=200` = ~15 requests = ~2.5% of /min cap. Manual sync hitting 4 profiles back-to-back (P2+ concern) = ~60 requests in <1 min; still under cap.
  - Mint flow: discogsography Settings UI `/settings/apps` only; no programmatic mint. Owner pastes plaintext into `gruvax-set-pat`.
  - Stats + timeline endpoints exist but are **not consumed by P1**.

- **Retry semantics, verbatim from refined spec, locked:**
  - 401/403 → raise `PATRejected` immediately, no retry. Sets `app_token_revoked = TRUE` + `last_sync_status = 'failed'` + `last_sync_error = 'pat_rejected'`.
  - 429 → honor `Retry-After` (seconds), then exponential backoff, max 3 retries. On exhaustion: `'rate_limited'`.
  - 5xx → exponential backoff, max 3 retries. On exhaustion: `'server_error'`.
  - Network errors → 1 retry then fail with `'network'`.

- **Sync flow (staging-swap), verbatim from refined spec § Sync flow:**
  1. Acquire pg advisory lock keyed on profile_id (skip if already held).
  2. `UPDATE profiles SET last_sync_status='in_progress'`.
  3. Stream rows from `client.iter_collection()` into `profile_collection_staging` temp table.
  4. On success, in a single transaction: `DELETE FROM profile_collection WHERE profile_id = :id; INSERT INTO profile_collection SELECT ... FROM staging; UPDATE profiles SET last_sync_at=NOW(), last_sync_status='ok', last_sync_item_count=count, discogsography_user_id = COALESCE(existing, :user_id_from_response), app_token_revoked = FALSE`.
  5. Drop staging temp table; release advisory lock.
  6. **In-process cache refresh inline** (D-14) — no SSE publish in P1.

- **Fernet PAT storage:** Use the standard `cryptography.fernet.Fernet(GRUVAX_SECRET_KEY)` pattern. Key generated with `Fernet.generate_key()` once per deployment; the deployment story for `GRUVAX_SECRET_KEY` is "operator generates once and pins in Compose `.env`; rotating means re-encrypting every profile row" — out of scope for P1 (no admin UI), in scope for a P4 utility.

- **Plain-text PAT NEVER logged at any level.** Logging middleware adds a redactor that masks any `Bearer dscg_*` substring in log records. Tested with a dedicated test case that asserts plaintext doesn't appear in captured logs even when the PAT is sent on a request that errors.

</specifics>

<deferred>
## Deferred Ideas

### Surfaced during discussion but belong in other phases / milestones
- **Multi-profile `discogsography_user_id` uniqueness enforcement in code** — P1 has only one profile so the partial-unique index never fires. P2's profile-manager UI is where the user-friendly error ("PAT belongs to user X who already has a profile") matters.
- **PAT rotation flow for the admin UI** — P1's `gruvax-set-pat` is the only path; P2 layers the equivalent in the profile manager (with the same strict user_id-match invariant).
- **Background sync scheduler + 3 sync triggers** — Spec puts all of this in **P4**. P1 has the manual `gruvax-sync` CLI; P2 will get the profile-manager "Sync now" button (UI sugar on the same endpoint); P4 wires the nightly `asyncio.create_task` loop + the cadence config.
- **Per-profile SSE channel `/api/events/{profile_id}`** — **P2**. P1's inline cache refresh is the placeholder.
- **401 reauth UI** (profile-list badge + kiosk inline banner) — **P4**, reading the `app_token_revoked` flag P1 sets.
- **Soft-delete cache-purge background task** — **P4**.
- **GRUVAX_SECRET_KEY rotation procedure / utility** — out of scope for P1; standalone CLI in a later phase if needed (most home deployments will never rotate).
- **Discogsography `stats` + `timeline` endpoint consumption** — out of scope; not needed for positioning. Possible future "collection insights" feature.
- **Switching profiles in the kiosk session** — P2's "Switch profile" corner button; out of P1.

### Reconciled risks (from refined spec)
- **Catalog# exposure (risk #1)** — RESOLVED via the contract artifact (P1 spike outcome: populated via `metadata` JSONB; no schema migration needed on discogsography side).
- **`profile_id` migration scope (risk #3)** — Reduced by D-11 spread across P1 (nullable) and P2 (NOT NULL); P1's round-trip invariant catches schema errors early.
- **PAT trust within household (risk #5)** — Acknowledged; P1's `gruvax-set-pat` is owner-pasted. Per-profile self-connect is **v2.1** (REQ-AUTH-02).

</deferred>

---

*Phase: 1-walking-skeleton-api-client-single-profile-sync*
*Context gathered: 2026-05-26*

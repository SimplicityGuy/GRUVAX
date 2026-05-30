# Phase 1: Walking skeleton — API client + single-profile sync - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-26
**Phase:** 1-walking-skeleton-api-client-single-profile-sync
**Areas discussed:** DGS-PREREQ status, Schema split for `profiles` + PAT storage, `gruvax-set-pat` CLI + first-sync trigger, `profile_id` migration timing across v1 tables, Dev/CI synthetic discogsography strategy

---

## DGS-PREREQ Status (precursor)

| Option | Description | Selected |
|--------|-------------|----------|
| Shipped — read it now | Contract is live. Read the artifact and reconcile drift before continuing the discussion. | ✓ |
| Still pending — proceed provisionally | Capture decisions against the spec's assumed contract; CONTEXT.md flags them provisional. | |
| Pause — DGS not ready | Stop now; don't write CONTEXT.md until contract lands. | |

**User's choice:** Shipped — read it now
**Notes:** Contract loaded from `/Users/Robert/Code/public/discogsography/docs/specs/v2-gruvax-integration.md` (v1, stable 2026-05-26). Drift reconciled in CONTEXT.md `<specifics>` and folded into D-03/D-04/D-13.

---

## Area 1 — Schema split for `profiles` + PAT storage

### Q1: How much of the `profiles` schema lands in P1?

| Option | Description | Selected |
|--------|-------------|----------|
| Full schema in P1 | Alembic migration creates the full table per spec; Fernet wiring lands once; P2 only adds FK fanout + admin UI. | ✓ |
| Minimal P1, expand in P2 | P1 creates only the columns needed for one profile; P2 adds soft-delete, unique indexes, etc. | |
| Minimal P1, plaintext-in-env (no Fernet) | PAT in env var until P2 forces per-row storage. | |

**User's choice:** Full schema in P1
**Notes:** Avoids a second `profiles` migration in P2. `GRUVAX_SECRET_KEY` boot-fail-if-missing lands now.

### Q2: PK for `profile_collection` given the missing `instance_id`

| Option | Description | Selected |
|--------|-------------|----------|
| PK = `(profile_id, release_id)` — collapse duplicates | Matches v1's de-facto dedup behavior but loses variants/dupes. | |
| PK = `(profile_id, release_id, folder_id)` | Composite preserves the "main vs wantlist-archive folder" duplicate case. | ✓ |
| Synthesize instance_id at sync time | Generate deterministic synthetic id; preserves N copies but no Discogs meaning. | |
| File a discogsography contract bug | Add instance_id upstream via contract minor-version bump; pause P1. | |

**User's choice:** PK = `(profile_id, release_id, folder_id)`
**Notes:** Honors the sketch-finding invariant about dupes/variants surfacing on purpose. Collapses two of the *same* release in the *same* folder, which Discogs models as `quantity`, not separate items.

### Q3: `last_sync_status` state machine

| Option | Description | Selected |
|--------|-------------|----------|
| 3 states + boolean flag | `{ok, failed, in_progress}` + `app_token_revoked BOOLEAN`. | ✓ |
| 4 states, no separate boolean | Add `'pat_rejected'` as 4th status; drop boolean. | |
| Status + structured error JSON | JSONB `last_sync_error`. | |

**User's choice:** 3 states + boolean flag
**Notes:** Matches refined spec verbatim. Boolean is the queryable signal P4's reauth-required badge reads.

### Q4 (continuation check): More questions or next area?

| Option | Selected |
|--------|----------|
| Next area | ✓ |
| More questions | |

---

## Area 2 — `gruvax-set-pat` CLI + first-sync trigger

### Q1: How does the PAT get into `gruvax-set-pat`?

| Option | Description | Selected |
|--------|-------------|----------|
| stdin only | Avoids shell history / `ps` / journald leakage. | ✓ |
| stdin OR `--pat` flag | Convenience for provisioning playbooks; warning to stderr. | |
| stdin OR env var (`DISCOGSOGRAPHY_PAT`) | stdin interactive; env var scripted. | |

**User's choice:** stdin only
**Notes:** Mirrors the discogsography mint UI's one-time-reveal carefulness.

### Q2: Does `gruvax-set-pat` also kick off the first full sync?

| Option | Description | Selected |
|--------|-------------|----------|
| Test sync inline + full sync triggered | Single command does verify + background full sync. | |
| Test sync inline, separate `gruvax-sync` for full | Two-step; owner sees full-sync output in terminal. | ✓ |
| Just store; sync via existing HTTP endpoint | curl against PIN-gated endpoint. | |
| Just store; full sync at next process restart | Lifespan hook triggers if `last_sync_at IS NULL`. | |

**User's choice:** Test sync inline, separate `gruvax-sync` for full
**Notes:** Cleanest UX for P1 with no admin UI. Owner watches sync progress in their shell.

### Q3: How does `gruvax-sync` reach the sync logic?

| Option | Description | Selected |
|--------|-------------|----------|
| Direct in-process | CLI opens its own pool, instantiates client + sync. | |
| Calls HTTP endpoint on running API | POST to a new PIN-gated `/api/admin/profiles/{id}/sync`. | ✓ |
| Spawns sync as a one-shot Compose service | `docker compose run --rm gruvax-sync`. | |

**User's choice:** Calls HTTP endpoint on the running API
**Notes:** One code path that P2's profile-manager Sync-now button and P4's nightly scheduler also hit. Snapshot can refresh in-process inline.

### Q4: `gruvax-set-pat` rerun semantics (rotation)

| Option | Description | Selected |
|--------|-------------|----------|
| Test-sync must succeed AND user_id must match | Strict; preserves the one-user-↔-one-profile invariant. | ✓ |
| Test-sync must succeed; user_id mismatch overwrites | Looser; creates a hole for P2's unique index. | |
| Always store, even if test-sync fails | Typoed PAT could clobber a working one. | |

**User's choice:** Test-sync must succeed AND user_id must match
**Notes:** Owner who really wants to switch must soft-delete first.

### Continuation check: More questions or next area?

| Option | Selected |
|--------|----------|
| Next area | ✓ |
| More questions | |

---

## Area 3 — `profile_id` migration timing across v1 tables

### Q1: How does P1 handle the 7 v1 tables that lack `profile_id`?

| Option | Description | Selected |
|--------|-------------|----------|
| Don't touch them in P1 | Smallest diff; v1 query code untouched. | |
| Add nullable `profile_id` now, NOT NULL in P2 | Spreads migration risk; P1 queries already speak profile_id. | ✓ |
| Hybrid: only kiosk-read tables in P1 | Spec-asymmetric, planning headache. | |

**User's choice:** Add nullable `profile_id` now, NOT NULL in P2
**Notes:** P2 becomes a pure schema-tightening change with no query-rewrite work.

### Q2: `OBSERVED_DISCOGSOGRAPHY_SCHEMA` cleanup

| Option | Description | Selected |
|--------|-------------|----------|
| Rip it out in P1 | Drop the setting; simplify search_path to `gruvax, public`. | ✓ |
| Keep env knob, default to `gruvax, public` | Backwards-compatible. | |
| Drop setting, keep configure callback shape | Hardcoded value in `_configure_connection`. | |

**User's choice:** Rip it out in P1
**Notes:** Matches the spirit of D7 (decouple GRUVAX from discogsography's DB).

### Q3: `/api/health` discogsography probe

| Option | Description | Selected |
|--------|-------------|----------|
| Rename + derive from last sync | `discogsography_api_check: ok | failed | stale`; no per-request egress. | ✓ |
| Rename + live probe | HEAD on each call with cached result. | |
| Keep field name; change meaning | `discogsography_view_check` name stays for API-stability. | |
| Drop entirely | Move to `/admin/diagnostics`. | |

**User's choice:** Rename to `discogsography_api_check`, derive from last sync
**Notes:** Preserves v1's "no live DB probe on /api/health" pattern.

### Q4: Cache refresh after sync (no SSE yet)

| Option | Description | Selected |
|--------|-------------|----------|
| Inline at end of sync | Same in-process refresh as lifespan startup. | ✓ |
| Pg LISTEN/NOTIFY now | Future-proof for multi-process; overkill for P1. | |
| Background polling of `last_sync_at` | 60s lag — bad UX for interactive sync. | |

**User's choice:** Inline at end of sync
**Notes:** P2 replaces the inline call with an SSE publish.

### Continuation check: More questions or next area?

| Option | Selected |
|--------|----------|
| Next area | ✓ |
| More questions | |

---

## Area 4 — Dev/CI synthetic discogsography strategy

### Q1: What replaces `gruvax_dev` schema as the stand-in?

| Option | Description | Selected |
|--------|-------------|----------|
| Tiered: respx (unit) + SQL fixtures (SLO) + real DGS (E2E) | Best fidelity-per-second-of-CI. | |
| Fake-discogsography FastAPI fixture | Real HTTP, real pagination, real `has_more`. | ✓ |
| Real local discogsography container in dev + respx in CI | Maximum dev realism; Compose footprint balloons. | |
| Keep `gruvax_dev` as SQL seed source only | Hybrid; coexists awkwardly with the OBSERVED_DISCOGSOGRAPHY_SCHEMA rip-out. | |

**User's choice:** Fake-discogsography FastAPI fixture
**Notes:** Justified given the contract's complexity (token routing, scope check, 429 simulation).

### Q2: How does dev seed `profile_collection`?

| Option | Description | Selected |
|--------|-------------|----------|
| Rewrite as `synth_profile_collection.sql` | Same rows, new shape; static seed. | |
| Generate from the fake-discogsography on dev `up` | Init-sync container; real sync end-to-end every boot. | ✓ |
| Keep `synth_collection.sql`, add a sync-it script | Hybrid; `gruvax_dev` schema lingers. | |

**User's choice:** Generate from the fake-discogsography on dev `up`
**Notes:** Slower dev `up`, but the real sync path is exercised on every clean boot. SLO tests still seed `profile_collection` via SQL (D-17) since they exercise positioning, not sync.

### Q3: Where does the discogsography endpoint URL live in prod?

| Option | Description | Selected |
|--------|-------------|----------|
| `DISCOGSOGRAPHY_BASE_URL` env var | Single env var, boot-validated; matches `MQTT_HOST` / `DATABASE_URL` pattern. | ✓ |
| Per-profile column on `profiles` | Premature flexibility for v2.0. | |
| Settings row in `gruvax.settings` table | Awkward boot dependency on DB content. | |

**User's choice:** `DISCOGSOGRAPHY_BASE_URL` env var
**Notes:** Tests override via `monkeypatch.setenv`.

### Q4: Alembic downgrade fidelity

| Option | Description | Selected |
|--------|-------------|----------|
| Full round-trip | Downgrade re-creates v_collection + grant. | ✓ |
| Forward-only with `raise NotImplementedError` | Breaks v1.0 CI invariant intentionally. | |
| Split into 2 migrations (additive + destructive) | Additive round-trips; destructive forward-only. | |

**User's choice:** Full round-trip
**Notes:** Preserves the v1.0 CI invariant called out in the `integration_test_harness` memory.

---

## Final check

| Option | Selected |
|--------|----------|
| I'm ready for context | ✓ |
| Explore more gray areas | |

**User's choice:** I'm ready for context

---

## Claude's Discretion

The following implementation details are left to the planner/executor — the user gave Claude flexibility:

- Exact admin PIN auth UX for `gruvax-sync` (single prompt vs `getpass` vs read-once-and-reuse).
- The fake-discogsography fixture's in-memory store seed format (YAML vs JSON vs Python literal).
- Exact log redaction strategy for the `Authorization` header (likely a structlog processor masking any `Bearer dscg_*`).
- Whether `gruvax-sync` prints progress as plain log lines or a TTY progress bar (plain log lines preferred for Compose-exec ergonomics).
- Extension to the `last_sync_error` tag set if a sync failure mode doesn't fit.

---

## Deferred Ideas

Captured in CONTEXT.md `<deferred>` section. Highlights:

- Multi-profile uniqueness UX → **P2**.
- Background sync scheduler + 3 sync triggers → **P4** (P1 has manual CLI only).
- Per-profile SSE channel → **P2** (P1 has inline cache refresh).
- 401 reauth UI → **P4**.
- Soft-delete cache-purge → **P4**.
- `GRUVAX_SECRET_KEY` rotation utility → later phase, not v2.0.
- Discogsography stats + timeline endpoint consumption → potential future "collection insights" feature.
- Kiosk profile-switching UI → **P2**.

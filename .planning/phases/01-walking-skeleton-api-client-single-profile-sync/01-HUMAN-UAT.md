---
status: complete
# 2026-05-27 complete: 5/5 tests pass. Test 1 unblocked after 6 compose-smoke sub-gap fixes
# landed (Plans 01-09, 01-10 + 4 inline fixes). Tests 2-4 validated against the now-healthy
# local stack. Test 5 (CI gate) green on run 26544940172 (HEAD 289cb29) after 6 additional
# CI-only sub-gap fixes (#8-#13). Total: 13 sub-gaps closed across this UAT round.
phase: 01-walking-skeleton-api-client-single-profile-sync
source: [01-VERIFICATION.md]
started: 2026-05-27T18:50:00Z
updated: 2026-05-27T23:35:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Compose-up clean-boot end-to-end (`just compose-smoke`)
expected: `docker compose down -v && docker compose up gruvax-api init-sync fake-discogsography` brings the stack up; init-sync's idempotency precheck either runs `gruvax-sync` against fake-discog OR (in dev compose) sees Plan 01-06's synth-seeded `profile_collection` and skips; exits 0. A second `docker compose up` of init-sync exits 0 with log line `"profile_collection already populated for default profile; skipping initial sync"`.
how: `just compose-smoke` (recipe in justfile:152) OR confirm the CI job at `.github/workflows/build.yml:116` is green at HEAD.
result: pass
notes: "Validated 2026-05-27 after 6 layered sub-gap fixes (Plans 01-09, 01-10, and inline fixes for httpx-dep, GRUVAX_ENV docs, psycopg precheck, just brace-escape). `just compose-smoke` exit 0; api/dev-pg/fake-discog/mosquitto all Healthy; init-sync first run exit 0; manual second-run `docker compose up init-sync` produced the exact skip log line and exit 0. Caveat: in dev compose both first AND second init-sync runs hit the skip path because Plan 01-06's synth seed (docker-entrypoint.sh:98-128) pre-populates `gruvax.profile_collection` before init-sync starts. The fake-discog → profile_collection real sync path is therefore dormant in dev compose and only exercised in production (no synth seed, real discogsography upstream). This is the intended design — the original UAT expected line predated Plan 01-06."

### 2. Kiosk staleness banner UI rendering (SC-5 sub-clause)
expected: With `profile_collection` populated and `profiles.last_sync_at` ≈ `now()`, kiosk shows no staleness banner. After `UPDATE gruvax.profiles SET last_sync_at = now() - INTERVAL '15 days'` (default profile) and waiting <60s for the next health-poll tick, kiosk renders the staleness banner with plain-language copy of the form `"Collection data may be outdated — last synced Nd ago"`. There is exactly ONE threshold (14 days) and ONE banner state per **D-01 LOCKED** (`frontend/src/routes/kiosk/StalenessBar.tsx:19`). A 4-day-old sync correctly shows NO banner (it is below the 14-day threshold). The v1.0 Phase 8 two-tier (3-day warning + 14-day critical) design did NOT survive the D-01 lock.
how: Open kiosk in Chromium against the running stack; manipulate `profiles.last_sync_at` via psql; observe banner state changes between fresh / 4-day / 15-day states.
result: pass
notes: "Validated 2026-05-27. Observed: (a) fresh `last_sync_at = now()` → no banner; (b) 4 days stale → no banner (correctly below 14-day threshold); (c) 15 days stale → banner present. Original UAT spec mistakenly carried forward v1.0 Phase 8's proposed two-tier design (3-day warning + 14-day critical), which was superseded by D-01's single-threshold lock. Spec corrected above to match the implemented behavior. Banner copy plain-language per UI-SPEC.md Surface 2."

### 3. `gruvax-set-pat` TTY no-echo behavior
expected: Running `gruvax-set-pat --profile default` in an interactive terminal prompts `"Paste PAT (input hidden):"` and the typed PAT is NOT echoed to the terminal. Piping `echo dscg_xxx | gruvax-set-pat --profile default` reads from stdin without prompt and does not require a TTY.
how: In a real PTY, run `gruvax-set-pat --profile default`; type a fake PAT and verify no echo; then verify history (`~/.zsh_history` or `~/.bash_history`) does NOT contain the PAT. Separately run the piped form and verify it succeeds.
result: pass
notes: "Validated 2026-05-27 (Part A only — interactive no-echo is the user-visible security guarantee; pipe-form and pure-stdin paths are covered by tests/integration/cli/test_set_pat.py). Observed: `uv run gruvax-set-pat --profile default` from host shell prompted `Paste PAT (input hidden):`; typed PAT was hidden (no characters echoed before Enter); subsequent network error from compose-internal hostname resolution was expected (DISCOGSOGRAPHY_BASE_URL points at fake-discogsography internal hostname; not reachable from host — irrelevant to the no-echo behavior which fires before any network call via getpass.getpass at set_pat.py:77)."

### 4. init-sync `GRUVAX_ADMIN_PIN` substitution fails compose-up if unset
expected: Running `docker compose up init-sync` WITHOUT `GRUVAX_ADMIN_PIN` in `.env` fails compose-up with a clear error mentioning the missing env var (the `${GRUVAX_ADMIN_PIN:?...}` substitution form).
how: Comment-out `GRUVAX_ADMIN_PIN` in `.env` (or unset env), then `docker compose up init-sync` — confirm compose exits non-zero with the missing-var error.
result: pass
notes: "Validated 2026-05-27. Two test forms: (1) shell-override `GRUVAX_ADMIN_PIN= docker compose up init-sync` → exit 1 with exact message from compose.yaml:306: `required variable GRUVAX_ADMIN_PIN is missing a value: GRUVAX_ADMIN_PIN must be set in .env for init-sync`. (2) Full .env temporarily moved aside → exit 1 with `required variable GRUVAX_SECRET_KEY is missing a value: GRUVAX_SECRET_KEY must be set in .env` — confirms defense-in-depth (multiple :? guards exist for mandatory secrets). No containers start in either case. .env restored after."

### 5. CI gate — `just slo` + `just migrate-roundtrip` on fresh `postgres:18` service
expected: CI's `just slo` step exits 0 with p95 `/api/search` ≤ 200ms and `/api/locate` ≤ 50ms on the synthetic dataset. CI's `just migrate-roundtrip` step exits 0 against a fresh `postgres:18` service (the in-repo dev DB fails locally due to environmental `boundary_history_source_check` violation from prior phases — documented as operator hygiene, NOT a Phase 1 gap).
how: Push the merge commit and observe the CI workflow. Confirm both steps green.
result: pass
notes: "Validated 2026-05-27 on run 26544940172 (HEAD 289cb29). All jobs green: run-code-quality, run-tests (slo + migrate-roundtrip + alembic round-trip), run-security (4 subjobs), build (compose-smoke). Six additional CI-only sub-gaps surfaced and were closed during this validation (post-Test 4): #8 yamllint indent-sequences in synth-data generator; #9 pre-commit cascade (RUF059 unused-var + mypy index error + hadolint pip-version-pin + 4 auto-fixers); #10 docker-compose-check hook needs CI placeholder secrets to resolve compose.yaml :? guards; #11 pgcrypto schema dep blocked downgrade-base (pinned to public + drop on downgrade in migration 0009); #12 SESSION_SECRET missing from api/init-sync environment block in compose.yaml; #13 GRUVAX_ENV unset in CI compose-smoke step caused Plan 01-10 entrypoint bootstrap to skip → migration 0002 crash on fresh postgres:18 volume."

## Summary

total: 5
passed: 5
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

- truth: "just compose-smoke brings the stack up clean and init-sync exits 0 with the idempotent skip log line on second run (SC-4 sub-clause)"
  status: resolved
  resolution: "Fixed by Plan 01-09 (removed duplicate `build:` block from init-sync service in compose.yaml). Merged. Plus 5 subsequent sub-gap fixes (httpx-runtime-dep, GRUVAX_ENV docs, init-sync psycopg precheck, just brace-escape ×2). Validated 2026-05-27: just compose-smoke exit 0; idempotent skip log line confirmed on second `docker compose up init-sync`."
  prior_status: failed
  reason: "User reported: just compose-smoke failed at docker build step — both `api` and `init-sync` services tag the same image name `ghcr.io/simplicityguy/gruvax:latest`. buildx exporter rejects the second push as duplicate (`target api: failed to solve: image already exists`). fake-discogsography built fine (`gruvax/fake-discogsography:dev`). compose-up never started."
  severity: blocker
  test: 1
  root_cause: "compose.yaml declares two services (`api` lines 44-58 and `init-sync` lines 249-257) that BOTH set `image: ghcr.io/simplicityguy/gruvax:latest` AND declare a `build:` block pointing at the same `context: .` + `dockerfile: Dockerfile`. `just compose-smoke` (justfile:155) invokes `docker compose up --build -d api fake-discogsography init-sync`, which triggers BuildKit to build both services in parallel and export each as the same image tag. The buildx exporter refuses the duplicate export with `target api: failed to solve: image \"ghcr.io/simplicityguy/gruvax:latest\": already exists`, killing the build before any container starts. fake-discogsography (lines 212-216) is unaffected because it uses a distinct tag `gruvax/fake-discogsography:dev`. This is an implementation deviation from Plan 01-05: PLAN.md line 449 explicitly specified `image: ghcr.io/simplicityguy/gruvax:latest   # reuses main gruvax image` with NO `build:` block for init-sync (intent: init-sync reuses the api-built image). The Task 3 GREEN commit (4dc644a) added a redundant `build:` block to init-sync that was not in the plan."
  artifacts:
    - path: "compose.yaml"
      line: "44-58"
      role: "api service — owns the canonical build of `ghcr.io/simplicityguy/gruvax:latest` (correct: both image: and build: are intentional per the build-or-pull comment on lines 46-51)"
    - path: "compose.yaml"
      line: "249-257"
      role: "init-sync service — BUG SITE: declares `image: ghcr.io/simplicityguy/gruvax:latest` (line 250) AND a `build:` block (lines 251-257) identical to the api service, causing the duplicate-tag export collision"
    - path: "compose.yaml"
      line: "212-216"
      role: "fake-discogsography service — reference for the correct pattern (distinct image tag `gruvax/fake-discogsography:dev`); proves separate-tag builds coexist fine"
    - path: "compose.yaml"
      line: "259-263"
      role: "init-sync depends_on already has `api: { condition: service_healthy }` — this guarantees api is built+healthy before init-sync starts, so removing init-sync's `build:` block is safe (api will have produced the tagged image first)"
    - path: ".planning/phases/01-walking-skeleton-api-client-single-profile-sync/01-05-PLAN.md"
      line: "448-449"
      role: "Plan 01-05 INTENT — explicitly specified `image: ghcr.io/simplicityguy/gruvax:latest   # reuses main gruvax image` for init-sync with NO build: block. Implementation in commit 4dc644a deviated by adding a redundant build: block."
    - path: ".planning/phases/01-walking-skeleton-api-client-single-profile-sync/01-05-SUMMARY.md"
      line: "103"
      role: "Records the deviating commit: `Task 3 GREEN: Dockerfile + server.py + compose.yaml + justfile + CI gate` — 4dc644a (feat)"
    - path: "justfile"
      line: "152-169"
      role: "compose-smoke recipe — line 155 uses `--build` which is what triggers the parallel duplicate-tag export. The recipe itself is correct; the underlying compose.yaml service definitions are the problem."
  missing:
    - "Remove `init-sync.build:` block (compose.yaml lines 251-257 inclusive — the `build:` key, `context: .`, `dockerfile: Dockerfile`, and the entire `args:` sub-block with GIT_SHA/BUILD_TIMESTAMP/GRUVAX_ENV)."
    - "Keep `init-sync.image: ghcr.io/simplicityguy/gruvax:latest` (line 250) — this is what makes init-sync REUSE the image api just built. Compose will not try to pull or rebuild because the tag is already present in the local daemon after the api service finishes building."
    - "Keep `init-sync.depends_on.api: { condition: service_healthy }` (lines 259-261) unchanged — this is what guarantees the api build completes before init-sync attempts to start, so the image tag exists when init-sync is launched."
    - "Add a 2-3 line YAML comment above `init-sync.image:` documenting that init-sync intentionally reuses the api image (no own `build:` block) — prevents a future contributor from re-introducing the duplicate build in pattern-matching with the api service block. Cite Plan 01-05 line 449 intent and the D-16 idempotent-precheck contract."
    - "After the fix, re-run `just compose-smoke` to confirm: (a) build step succeeds without the duplicate-image error, (b) init-sync exits 0 on first boot with `running initial sync` log line, (c) a second `just compose-smoke` (with no `down -v` between) exits 0 with the `profile_collection already populated for default profile; skipping initial sync` log line (D-16 idempotency), (d) the assertion that fake-discogsography serves rows succeeds."
    - "Unblock dependent UAT tests 2, 3, 4, 5 (currently marked `skipped` with reason `blocked by Test 1 compose build failure`) — re-run each after the compose-smoke fix lands."
    - "Optional regression guard (LOW priority — only if the planner wants a structural test): extend `tests/integration/test_compose_smoke.py` with an assertion that no two services share the same `image:` tag when both have `build:` blocks. This prevents the bug from recurring in future compose.yaml edits."

- truth: "just compose-smoke completes alembic upgrade head on a fresh postgres:18 and the api container reaches healthy state (SC-5 sub-clause)"
  status: resolved
  resolution: "Fixed by Plan 01-10 (added dev-only gruvax_dev stub schema bootstrap to docker-entrypoint.sh before alembic upgrade). Merged. Plan 01-06 synth seed (already present) then populates gruvax.profile_collection. Validated 2026-05-27: api container reaches Healthy in ~16s; alembic upgrade chain (including 0009's DROP of v_collection) completes cleanly."
  prior_status: failed
  reason: "After Plan 01-09 unblocked the duplicate-image-tag build error, `just compose-smoke` reached the api container's entrypoint, where `alembic upgrade head` crashed during migration 0002 with `relation \"collection_items\" does not exist`. Migration 0002's CREATE VIEW body references unqualified `collection_items / releases / artists` which `search_path` resolves to `gruvax_dev.*` (dev/CI) or `discogsography.*` (prod) — neither schema exists in a fresh compose `postgres:18` volume, so the upgrade chain crashes BEFORE migration 0009 gets a chance to DROP the view per D-19."
  severity: blocker
  test: 1
  root_cause: "D-12 simplified the runtime pool's search_path to a single literal `gruvax, public` so a single view body could resolve to either gruvax_dev (dev/CI) or discogsography (prod) via the public-search-path fallback. The dev workflow (`integration_test_harness` memory) hand-seeds `gruvax_dev.*` out of band before tests run, so the missing schema never surfaced. Compose-smoke is the first path that exercises a virgin postgres:18 volume — there is no equivalent bootstrap step for `gruvax_dev` in `docker-entrypoint.sh`, so 0002's `CREATE VIEW gruvax.v_collection AS SELECT ... FROM collection_items ...` errors at parse time when neither schema exists. The synth-seed block at the bottom of the same entrypoint script demonstrates the pattern (GRUVAX_ENV=development guard + idempotent DDL) but only fires AFTER alembic completes, so it cannot solve a pre-alembic schema-existence problem."
  artifacts:
    - path: "docker-entrypoint.sh"
      line: "28-94"
      role: "FIX SITE: insertion site for the gruvax_dev bootstrap block, between line 27 `echo \"Database is up.\"` and the alembic-upgrade line. The new block adds (a) a 27-line explanatory comment, (b) a `GRUVAX_ENV:-production` guard matching the existing synth-seed guard pattern verbatim, (c) heredoc-piped psycopg.connect() that runs idempotent `CREATE SCHEMA IF NOT EXISTS gruvax_dev` + three `CREATE TABLE IF NOT EXISTS` statements for collection_items / releases / artists with the exact column shapes migration 0002's view body references."
    - path: "migrations/versions/0002_v_collection_view.py"
      line: "39-55"
      role: "Failing migration — the `_CREATE_VIEW` SQL body references unqualified `collection_items / releases / artists` resolved via search_path. Authoritative spec for which columns the stub tables MUST expose. NOT MODIFIED by 01-10 (Option B is out of scope — would require either schema-qualifying the view or splitting it into two env-conditional bodies, both larger blast radius than the entrypoint bootstrap)."
    - path: "migrations/versions/0009_v2_profiles_and_collection_cache.py"
      line: "217"
      role: "`_DROP_V_COLLECTION` per D-19 — the migration that retires the view once the chain completes. Once 0002 stops crashing, 0009 runs and drops the view, after which the stub tables become dead weight (intended end state for compose-only scope)."
    - path: "tests/fixtures/legacy/synth_collection.sql"
      line: "19-46"
      role: "Column-shape spec the bootstrap stubs mirror. Existing dev seed creates `gruvax_dev.{artists, releases, collection_items}` with richer columns/constraints (BIGSERIAL, FK to artists, NOT NULL, indices). The bootstrap's `CREATE TABLE IF NOT EXISTS` is a no-op when this seed has already run; the stubs are minimal-column placeholders for the compose-virgin-volume case only."
    - path: "compose.yaml"
      line: "44-58"
      role: "api service definition — currently does NOT set GRUVAX_ENV in the `environment:` block; it only passes it as a build-arg into `_version.py`. For the bootstrap (and the existing synth-seed) to fire under compose-smoke, the operator's `.env` must include `GRUVAX_ENV=development` OR the api service's `environment:` block must be extended to inherit it. NOT MODIFIED by 01-10 (scope-limited to entrypoint + UAT doc); flagged as operator hygiene for the post-merge re-run."
    - path: ".planning/phases/01-walking-skeleton-api-client-single-profile-sync/01-CONTEXT.md"
      line: "D-12"
      role: "Decision: simplified pool search_path to `gruvax, public`. Explains why the bootstrap goes into `gruvax_dev` (the public-search-path fallback target for the dev environment) and is dev-only (production fallback target is `discogsography`, owned externally)."
  missing:
    - "Insert dev-only gruvax_dev bootstrap step in `docker-entrypoint.sh` between the database-up wait (line 27) and the `alembic upgrade head` invocation (formerly line 30). Block must include: (a) a citation-rich comment naming Plan 01-10, the migration-0002 unqualified-table-ref problem, D-12's search_path simplification, D-19's eventual DROP, and an explicit STUB-only warning; (b) `if [ \"${GRUVAX_ENV:-production}\" = \"development\" ]; then ... fi` guard matching the existing synth-seed guard pattern verbatim; (c) heredoc-piped `psycopg.connect()` running `CREATE SCHEMA IF NOT EXISTS gruvax_dev` + idempotent `CREATE TABLE IF NOT EXISTS` for collection_items / releases / artists with the minimum columns the view body references."
    - "Production safety: the GRUVAX_ENV=development guard makes the bootstrap a no-op in production. Verified via `GRUVAX_ENV=production timeout 5 bash -x docker-entrypoint.sh 2>&1 | head -20 | grep -q 'CREATE SCHEMA IF NOT EXISTS gruvax_dev'` returning non-zero (bootstrap line ABSENT from trace)."
    - "Idempotency: `CREATE SCHEMA IF NOT EXISTS` + `CREATE TABLE IF NOT EXISTS` make the bootstrap a no-op on dev DBs already seeded by `tests/fixtures/legacy/synth_collection.sql` (richer columns/constraints preserved)."
    - "After the fix lands, re-run `just compose-smoke` to confirm: (a) api container boot log includes `Ensuring gruvax_dev stub schema for migration 0002 (dev-only)...` followed by `gruvax_dev stub tables ensured (idempotent; required for migration 0002 v_collection view).`, (b) `alembic upgrade head` completes through migration 0009 (visible in `docker compose logs api`), (c) `docker inspect gruvax-init-sync --format '{{.State.ExitCode}}'` returns 0, (d) fake-discogsography serves rows."
    - "Operator hygiene: confirm `.env` includes `GRUVAX_ENV=development` (or compose.yaml's api `environment:` block inherits it) so the runtime bootstrap actually fires under compose-smoke. This is NOT a 01-10 deliverable (scope-locked to entrypoint + UAT doc); flagged here so the post-merge re-run does not silently skip the bootstrap and re-encounter the migration-0002 crash."
    - "Re-run UAT Tests 2, 3, 4, 5 (currently `skipped` with `reason: blocked by Test 1 compose build failure`) — the second sub-blocker is now resolved and the full stack reaches healthy state for downstream test exercise."

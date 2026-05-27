---
status: partial
# All 4 skipped tests have an explicit `reason:` ("blocked by Test 1 compose build failure"),
# so per verify-work.md `complete_session` rules the session is technically `complete` —
# but 4/5 tests deferred to a real-PTY / live-stack environment that depends on Test 1 unblocking,
# so `partial` better reflects the user-visible state.
phase: 01-walking-skeleton-api-client-single-profile-sync
source: [01-VERIFICATION.md]
started: 2026-05-27T18:50:00Z
updated: 2026-05-27T19:05:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Compose-up clean-boot end-to-end (`just compose-smoke`)
expected: `docker compose down -v && docker compose up gruvax-api init-sync fake-discogsography` brings the stack up; init-sync's idempotency precheck returns 0 rows; runs `gruvax-sync`; populates `profile_collection` with ~3000 rows from the fake-discogsography seed; exits 0. A second `docker compose up` of init-sync exits 0 with log line `"profile_collection already populated for default profile; skipping initial sync"`.
how: `just compose-smoke` (recipe in justfile:152) OR confirm the CI job at `.github/workflows/build.yml:116` is green at HEAD.
result: issue
reported: "just compose-smoke failed at the docker build step with: target api: failed to solve: image \"ghcr.io/simplicityguy/gruvax:latest\": already exists. The init-sync and api services are both tagging the same image name (ghcr.io/simplicityguy/gruvax:latest), causing the buildx exporter to refuse the second push as duplicate. fake-discogsography image built fine (gruvax/fake-discogsography:dev). compose-up never got past the build phase."
severity: blocker

### 2. Kiosk staleness banner UI rendering (SC-5 sub-clause)
expected: With `profile_collection` populated and `profiles.last_sync_at` ≈ `now()`, kiosk shows no staleness banner. After `UPDATE gruvax.profiles SET last_sync_at = now() - INTERVAL '4 days'` (default profile) and waiting <60s, kiosk renders the >3-day staleness banner (per v1.0 Phase 8 thresholds carried forward, per SYN-02). After >14 days ago, kiosk renders the critical banner.
how: Open kiosk in Chromium against the running stack; manipulate `profiles.last_sync_at` via psql; observe banner state changes.
result: skipped
reason: "blocked by Test 1 compose build failure"

### 3. `gruvax-set-pat` TTY no-echo behavior
expected: Running `gruvax-set-pat --profile default` in an interactive terminal prompts `"Paste PAT (input hidden):"` and the typed PAT is NOT echoed to the terminal. Piping `echo dscg_xxx | gruvax-set-pat --profile default` reads from stdin without prompt and does not require a TTY.
how: In a real PTY, run `gruvax-set-pat --profile default`; type a fake PAT and verify no echo; then verify history (`~/.zsh_history` or `~/.bash_history`) does NOT contain the PAT. Separately run the piped form and verify it succeeds.
result: skipped
reason: "blocked by Test 1 compose build failure"

### 4. init-sync `GRUVAX_ADMIN_PIN` substitution fails compose-up if unset
expected: Running `docker compose up init-sync` WITHOUT `GRUVAX_ADMIN_PIN` in `.env` fails compose-up with a clear error mentioning the missing env var (the `${GRUVAX_ADMIN_PIN:?...}` substitution form).
how: Comment-out `GRUVAX_ADMIN_PIN` in `.env` (or unset env), then `docker compose up init-sync` — confirm compose exits non-zero with the missing-var error.
result: skipped
reason: "blocked by Test 1 compose build failure"

### 5. CI gate — `just slo` + `just migrate-roundtrip` on fresh `postgres:18` service
expected: CI's `just slo` step exits 0 with p95 `/api/search` ≤ 200ms and `/api/locate` ≤ 50ms on the synthetic dataset. CI's `just migrate-roundtrip` step exits 0 against a fresh `postgres:18` service (the in-repo dev DB fails locally due to environmental `boundary_history_source_check` violation from prior phases — documented as operator hygiene, NOT a Phase 1 gap).
how: Push the merge commit and observe the CI workflow. Confirm both steps green.
result: skipped
reason: "blocked by Test 1 compose build failure"

## Summary

total: 5
passed: 0
issues: 1
pending: 0
skipped: 4
blocked: 0

## Gaps

- truth: "just compose-smoke brings the stack up clean and init-sync exits 0 with the idempotent skip log line on second run (SC-4 sub-clause)"
  status: failed
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

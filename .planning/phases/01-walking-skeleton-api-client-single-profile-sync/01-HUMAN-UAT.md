---
status: partial
phase: 01-walking-skeleton-api-client-single-profile-sync
source: [01-VERIFICATION.md]
started: 2026-05-27T18:50:00Z
updated: 2026-05-27T18:50:00Z
---

## Current Test

[awaiting human testing — start with `## Tests` items in order]

## Tests

### 1. Compose-up clean-boot end-to-end (`just compose-smoke`)
expected: `docker compose down -v && docker compose up gruvax-api init-sync fake-discogsography` brings the stack up; init-sync's idempotency precheck returns 0 rows; runs `gruvax-sync`; populates `profile_collection` with ~3000 rows from the fake-discogsography seed; exits 0. A second `docker compose up` of init-sync exits 0 with log line `"profile_collection already populated for default profile; skipping initial sync"`.
how: `just compose-smoke` (recipe in justfile:152) OR confirm the CI job at `.github/workflows/build.yml:116` is green at HEAD.
result: [pending]

### 2. Kiosk staleness banner UI rendering (SC-5 sub-clause)
expected: With `profile_collection` populated and `profiles.last_sync_at` ≈ `now()`, kiosk shows no staleness banner. After `UPDATE gruvax.profiles SET last_sync_at = now() - INTERVAL '4 days'` (default profile) and waiting <60s, kiosk renders the >3-day staleness banner (per v1.0 Phase 8 thresholds carried forward, per SYN-02). After >14 days ago, kiosk renders the critical banner.
how: Open kiosk in Chromium against the running stack; manipulate `profiles.last_sync_at` via psql; observe banner state changes.
result: [pending]

### 3. `gruvax-set-pat` TTY no-echo behavior
expected: Running `gruvax-set-pat --profile default` in an interactive terminal prompts `"Paste PAT (input hidden):"` and the typed PAT is NOT echoed to the terminal. Piping `echo dscg_xxx | gruvax-set-pat --profile default` reads from stdin without prompt and does not require a TTY.
how: In a real PTY, run `gruvax-set-pat --profile default`; type a fake PAT and verify no echo; then verify history (`~/.zsh_history` or `~/.bash_history`) does NOT contain the PAT. Separately run the piped form and verify it succeeds.
result: [pending]

### 4. init-sync `GRUVAX_ADMIN_PIN` substitution fails compose-up if unset
expected: Running `docker compose up init-sync` WITHOUT `GRUVAX_ADMIN_PIN` in `.env` fails compose-up with a clear error mentioning the missing env var (the `${GRUVAX_ADMIN_PIN:?...}` substitution form).
how: Comment-out `GRUVAX_ADMIN_PIN` in `.env` (or unset env), then `docker compose up init-sync` — confirm compose exits non-zero with the missing-var error.
result: [pending]

### 5. CI gate — `just slo` + `just migrate-roundtrip` on fresh `postgres:18` service
expected: CI's `just slo` step exits 0 with p95 `/api/search` ≤ 200ms and `/api/locate` ≤ 50ms on the synthetic dataset. CI's `just migrate-roundtrip` step exits 0 against a fresh `postgres:18` service (the in-repo dev DB fails locally due to environmental `boundary_history_source_check` violation from prior phases — documented as operator hygiene, NOT a Phase 1 gap).
how: Push the merge commit and observe the CI workflow. Confirm both steps green.
result: [pending]

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps

(none recorded yet — populated by `/gsd-verify-work 1` when issues surface)

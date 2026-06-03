# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v2.1 — Resilience + Privacy + UX polish

**Shipped:** 2026-06-03
**Phases:** 5 (6–10) | **Plans:** 16 | **Timeline:** 2026-05-30 → 2026-06-03

### What Was Built
- Profile-scoped boundary writes (DATA-01) + live device revoke/reassign over SSE (DEV-05).
- Member self-connect via single-use invite links — members supply their own PAT; owner never sees it (AUTH-02) + post-sync collection-diff "N new records" (API-04).
- QR pairing alongside the 4-digit PIN, session-only search history, no-PIN kiosk reset, log query-redaction (DEV-04 / PRIV-01..04 / SRCH-09).
- SSE-authoritative offline banner + degraded mode + backoff/jitter reconnect + stale-data refresh (OFF-01..04).
- Admin mini-Kallax per-cube fill/occupancy shading with live reshade (UX-01).

### What Worked
- **Vertical MVP slicing held up** — every phase shipped a user-observable capability; no horizontal infra-only phases.
- **Retroactive close-out caught real gaps** — verifying the milestone before archiving surfaced an un-run live UAT and a missing Nyquist doc; closing them took one focused session.
- **Playwright two-tab UAT** (kiosk + admin, shared cookie context) deterministically verified the device-lifecycle behaviors that unit tests could only prove at the signal level — a DOM-observer pattern captured transient overlays/banners that would otherwise be missed.

### What Was Inefficient
- **Phantom phase 999.1** lingered as an empty directory after its scope was promoted into Phase 10, and `roadmap.analyze` surfaced it as "pending" — needed manual cleanup at close.
- **Audit went stale between run and archive** — its #1 tech-debt item (DEV-05 live UAT) was already closed by the time of archive; had to reconcile the audit status manually.
- **CLI accomplishment extraction produced junk** — `milestone.complete` grabbed literal `"One-liner:"` header lines from SUMMARYs; the MILESTONES entry had to be rewritten by hand.
- **`requirements-completed` SUMMARY frontmatter was under-populated** (14/16) through the milestone, so the cross-check field wasn't a reliable coverage source until backfilled at close.

### Patterns Established
- **DOM-observer UAT for transient UI** — arm a `MutationObserver` that records fleeting overlay/banner text before triggering the event from another tab; survives SPA client-side navigation.
- **Worktree exception for test-dependent quick tasks** — when a quick task must run a suite that needs gitignored deps (`node_modules`), run it on the main tree, not an isolated worktree.
- **Close debt before archive** — treat a `tech_debt` audit as a punch-list to clear (or consciously accept) at milestone close rather than carrying it silently forward.

### Key Lessons
1. Promote-from-backlog should *delete* the originating placeholder directory, or roadmap analysis will keep reporting it as pending work.
2. Re-verify and re-stamp the milestone audit immediately before archive — point-in-time audits drift once debt is worked.
3. Don't trust auto-extracted accomplishment text; the SUMMARY one-liner heuristic is fragile — review the MILESTONES entry before committing.

### Cost Observations
- Model mix: planning on opus, execution on sonnet (balanced profile).
- Close-out was one session: Playwright UAT + 1 quick task (W-1/W-2/frontmatter) + Nyquist doc + archive.
- Notable: the most expensive verification (live device lifecycle) was the highest-value — it was the last unproven requirement in the milestone.

---

## Milestone: v2.0 — Multi-User Collections

**Shipped:** 2026-05-30
**Phases:** 5 | **Plans:** 35 | **Timeline:** 2026-05-26 → 2026-05-30 (5 days)

### What Was Built
- Re-architecture off the `gruvax.v_collection` cross-schema read onto discogsography's **HTTP API** with per-user scoped PATs (`DiscogsographyClient` + Fernet PAT-at-rest + structlog redactor); positioning/search now run off a local `profile_collection` cache populated by an advisory-locked staging-swap sync.
- Full **multi-profile** model: migrations 0009/0010 (`profiles`, `profile_collection`, `profile_id NOT NULL` on 5 data tables); per-profile cache/bus/SSE channel keyed by `profile_id` (cross-profile leakage impossible by construction); browse-binding session + picker; profile-manager admin UI.
- **Devices + pairing** (migration 0011): 4-digit code flow (<30s, hardware-UAT confirmed), HttpOnly fingerprint cookie persistent across reboot, devices admin UI, Pi provisioning artifacts.
- **Sync autonomy**: DST-safe nightly scheduler (configurable cadence), 401 re-auth surfacing, per-profile diagnostics cards, soft-delete cache-purge, Sync-now progress/toast.
- **Closure phase (Phase 5)**: B-01 kiosk `collection_changed` listener + B-02 `profile_id`-optional search/locate — wired the two cross-phase seams the milestone audit surfaced.

### What Worked
- **Closure-phase pattern (carried from v1.0 Phase 10).** The milestone re-audit found 2 cross-phase blockers (B-01, B-02) that no single per-phase verification caught; absorbing them in a dedicated 2-plan Phase 5 — rather than retrofitting P1–P4 — moved the audit from `gaps_found` → `tech_debt` cleanly.
- **Building against a canonical fake-discogsography contract fixture.** Decoupling from the in-flight discogsography v2 work let all 5 phases plan, execute, and verify on GRUVAX's own clock with zero contract-stub drift; the same fixture doubles as the Compose sibling service.
- **Structural data isolation.** Keying caches/buses/SSE on `profile_id` made OOS-04 (no cross-profile visibility) a property of the architecture instead of a filter to remember in every handler.
- **Wave-0 RED scaffolding per phase.** Each phase opened with a test-only plan establishing the Nyquist baseline before any Wave-1 implementation — kept TDD discipline visible at the wave gate.

### What Was Inefficient
- **Phase-contract changes silently broke ~60 Phase 1 tests.** Per-plan verification only checks *new* tests, so a P2 contract change regressed earlier-phase tests undetected until a full sequential run. Lesson: run the FULL suite after each wave merge, not just the wave's new tests. (project memory: `project_p02_p1_test_regression_pattern`)
- **Worktree base drift + SUMMARY leak repeatedly blocked the cleanup wave.** A wave's worktree forked from a stale squash-PR base; executor `SUMMARY.md` leaked untracked into the main tree; cleanup refused branches containing deletions. Each needed a manual `git merge --no-ff` rescue. (memories: `project_execute_phase_worktree_base_drift`, `project_execute_phase_summary_leak_blocks_cleanup`, `project_worktree_cleanup_deletions`)
- **A compose/deploy-flip validation step destroyed the shared dev Postgres volume mid-run**, surfacing as PoolTimeout → phantom_boundary; required a reseed dance. (memory: `project_compose_flip_teardown_dev_db`)
- **Governance artifacts (SECURITY.md, VALIDATION.md) lagged the code** and had to be reconstructed retroactively at audit time (all resolved 2026-05-30, but after the fact).
- **SUMMARY one-liner field drift** — many phase SUMMARYs didn't populate the field `summary-extract` reads, so the milestone-complete CLI emitted garbage accomplishments that had to be hand-rewritten.

### Patterns Established
- **Closure phase for milestone-audit seams** is now a repeatable GRUVAX convention (v1.0 Phase 10 → v2.0 Phase 5).
- **Fake-contract-fixture-first** for cross-repo dependencies: model the upstream contract as an in-process fixture that also serves as the Compose sibling, so downstream work never blocks on the upstream clock.
- **Per-profile registries keyed on a single id** as the isolation primitive.
- **Full sequential test run after every wave merge** (not per-plan only) to catch cross-phase contract regressions.

### Key Lessons
1. Per-plan verification is necessary but not sufficient — a contract change in a later phase can silently regress earlier-phase tests. Gate each wave merge on the full suite.
2. Worktree-isolated parallel execution is a net win but has sharp edges (base drift, untracked-file leaks, deletion-containing branches); budget for occasional manual `git merge --no-ff` rescues and never let a validation step touch the shared dev DB volume.
3. Run `/gsd-secure-phase` and `/gsd-validate-phase` *as part of each phase*, not at milestone-audit time — retroactive governance reconstruction is avoidable rework.
4. Decoupling from an in-flight sibling repo via a canonical contract fixture is the right call — it preserved velocity and produced zero stub drift.

### Cost Observations
- Model mix: predominantly Opus for planning/execution (balanced model profile); not separately metered.
- Notable: 169 commits / 35 plans over 5 days with worktree-parallel waves — high throughput, with the cleanup-wave manual rescues as the main friction tax.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0 MVP | 10 | 50 | Vertical MVP slicing established; closure-phase pattern introduced (Phase 10) |
| v2.0 Multi-User | 5 | 35 | Phase numbering reset per milestone; worktree-parallel waves; fake-contract-fixture for cross-repo decoupling; closure phase reused (Phase 5) |

### Cumulative Quality

| Milestone | Requirements satisfied | Audit close status | Zero-dep / latest-stack discipline |
|-----------|------------------------|--------------------|-----------------------------------|
| v1.0 | 75 / 75 in-scope (9 SPIDR-deferred) | gaps_found → closed via Phase 10 | Python 3.13, Vite 8, Postgres 18, mosquitto:latest |
| v2.0 | 12 / 12 active (AUTH-01 deferred) | gaps_found → tech_debt (no blockers) | + httpx/stamina, Fernet, structlog |

### Top Lessons (Verified Across Milestones)

1. **The closure-phase pattern works.** Both milestones ended `gaps_found` at audit and were brought home by a dedicated audit-driven closure phase rather than scattered retrofits.
2. **Run the full test suite after each wave merge.** v2.0's ~60-test Phase-1 regression confirms per-plan verification alone misses cross-phase contract breaks.
3. **Latest-stack-always pays off** (per user feedback memory) — clean dependency story across both milestones, no version-split maintenance.

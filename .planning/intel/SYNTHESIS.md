# Intel — Synthesis Summary

**Generated:** 2026-05-26
**Mode:** merge (v1.0 closed; v2.0 milestone scope being introduced)
**Source manifest:** `.planning/intel/ingest-manifest.yaml`
**Conflicts report:** `.planning/INGEST-CONFLICTS.md`

This file is the single entry point for `gsd-roadmapper`. Read it first, then walk into the per-type intel files below.

---

## Doc counts by type

| Type    | Count |
|---------|-------|
| ADR     | 0     |
| SPEC    | 1     |
| PRD     | 0     |
| DOC     | 0     |
| UNKNOWN | 0     |
| **Total** | **1** |

Sources:
- `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` — SPEC (precedence 0 via manifest override), confidence high.

The single SPEC has zero outbound cross-references, so cycle detection is trivially clean.

---

## Decisions extracted

**Count:** 8 (D1–D7 + D-meta cross-repo framing)
**Locked (GSD sense):** 0 — the spec is `locked: false`. Its internal "Locked Decisions" header is design-phase language only.

| ID     | Scope                                                      | Relationship to v1.0                                             |
|--------|------------------------------------------------------------|------------------------------------------------------------------|
| D1     | v2.0 deployment topology                                   | Extends — central server already exists; profiles concept is new |
| D2     | discogsography PAT scope `collection:read`                 | New — cross-repo                                                  |
| D3     | single-PIN owner manages profiles                          | Extends v1 single-PIN auth (no contradiction)                    |
| D4     | shelving is per-profile                                    | Extends v1 boundary/segment/LED/stats tables                     |
| D5     | shelving layout belongs to profile, not device             | New — devices concept is new                                     |
| D6     | pull-and-cache collection access                           | **supersedes-on-v2-milestone** of v1 `v_collection` model        |
| D7     | retire `gruvax.v_collection` + read-only grant             | **supersedes-on-v2-milestone** of v1 contact-surface decision    |
| D-meta | cross-repo milestone framing                               | New — gates v2.0 walking skeleton                                 |

Full text: `.planning/intel/decisions.md`.

---

## Requirements extracted

**Count:** 18 (5 discogsography-side + 12 GRUVAX-side + 1 deferred + 8 v1.x housekeeping with reconciliation needed)

### v2.0 — discogsography-side (5)
- REQ-app-tokens-table
- REQ-app-token-settings-ui
- REQ-require-app-token-dependency
- REQ-catalog-number-exposure  *(HIGH risk; gates GRUVAX walking skeleton)*
- REQ-token-rate-limiting

### v2.0 — GRUVAX-side (12)
- REQ-profiles-table
- REQ-profile-manager-admin-ui
- REQ-v1-default-profile-migration
- REQ-api-client-paged-sync
- REQ-sync-triggers
- REQ-positioning-runs-off-local-cache
- REQ-phase8-staleness-redefinition
- REQ-profile-id-migration
- REQ-devices-table
- REQ-rpi-device-binding
- REQ-kiosk-pairing-provisioning
- REQ-retire-v-collection

### v2.0 — deferred / optional (1)
- REQ-oauth2-device-grant

### v1.x housekeeping — reconciliation needed (8)
- REQ-structlog-migration
- REQ-env-driven-log-level
- REQ-github-workflows
- REQ-dependabot
- REQ-pre-commit-config
- REQ-update-project-script
- REQ-docs-refresh-strip-lux-nox
- REQ-lint-debt-pass

The Phase 9 / v1.x bucket above is the WARNING in the conflicts report. MILESTONES.md records these as shipped at v1.0 close; user-memory cites residual work on `chore/align-discogsography-tooling`. Roadmapper must reconcile before scheduling.

Full text: `.planning/intel/requirements.md`.

---

## Constraints extracted

**Count:** 11

| Type          | Count | IDs                                                                                                            |
|---------------|-------|----------------------------------------------------------------------------------------------------------------|
| schema        | 5     | CON-app-tokens-schema, CON-profiles-schema, CON-devices-schema, CON-profile-id-fk-fanout, CON-collection-cache-fields |
| api-contract  | 1     | CON-discogsography-api-surface                                                                                 |
| protocol      | 2     | CON-pat-bearer-flow, CON-rpi-binds-to-one-profile                                                              |
| nfr           | 3     | CON-200ms-slo-preserved, CON-offline-resilience-preserved, CON-staleness-redefinition, CON-rate-limit-collection-api  |

(CON-rate-limit-collection-api also fits nfr — actual nfr count is 4; the table above merges it into nfr.)

Full text: `.planning/intel/constraints.md`.

---

## Context topics

**Count:** 8

- v1.0 single-collection assumption (background)
- Why v2.0 is a milestone, not a phase
- discogsography current reality (verified 2026-05-25)
- Data flow narrative (with embedded Mermaid sequence diagram)
- Phase decomposition (v2.0)
- Phase 9 (v1.x housekeeping) — flagged with cross-link to WARNING
- Risks & open questions carried from spec
- v2.0 also opens a path for v1-deferred reqs (synthesizer cross-reference to `milestones/v1.0-REQUIREMENTS.md` deferred items: SRCH-09, OFF-01..04, PRIV-01..04)

Full text: `.planning/intel/context.md`.

---

## Conflicts summary

| Bucket             | Count |
|--------------------|-------|
| BLOCKER            | 0     |
| WARNING            | 1     |
| INFO (auto-resolved) | 5     |

- **Blockers:** none — no LOCKED-vs-LOCKED contradictions, no cycles, no UNKNOWN docs.
- **Warning:** Phase 9 housekeeping scope-vs-MILESTONES.md reconciliation (see `INGEST-CONFLICTS.md` for the action). User must confirm whether Phase 9 closed cleanly before deciding which (if any) of REQ-structlog-migration / REQ-env-driven-log-level / REQ-github-workflows / REQ-dependabot / REQ-pre-commit-config / REQ-update-project-script / REQ-docs-refresh-strip-lux-nox / REQ-lint-debt-pass land on the v2.0 roadmap vs. a separate v1.x wrap-up.
- **Auto-resolved (INFO):** five entries documenting (a) v1-`v_collection`-retirement as a milestone-boundary scope expansion, (b) single-PIN-extends-into-profile-manager as scope expansion, (c) staleness signal redefinition without contract change, (d) single-doc ingest = no cross-doc precedence resolution, (e) catalog-number-exposure HIGH risk surfaced for roadmapper attention (not a doc conflict).

Full report: `.planning/INGEST-CONFLICTS.md`.

---

## Pointers

- `.planning/intel/decisions.md`     — 8 decisions (none GSD-locked)
- `.planning/intel/requirements.md`  — 18 candidate requirements, 8 of which need housekeeping reconciliation
- `.planning/intel/constraints.md`   — 11 constraints (5 schema, 1 api-contract, 2 protocol, 3 nfr, 1 rate-limit nfr)
- `.planning/intel/context.md`       — 8 context topics
- `.planning/INGEST-CONFLICTS.md`    — 0 BLOCKER / 1 WARNING / 5 INFO

---

## Downstream guidance for `gsd-roadmapper`

1. **The WARNING is not a hard gate but must be addressed before final routing.** Confirm Phase 9 closure with the user; the 8 v1.x housekeeping requirements may either be confirmed-shipped (drop from roadmap) or split into a small v1.x wrap-up that runs in parallel with v2.0 Phase 1.
2. **v2.0 Phase 1 (discogsography-side) is the only true cross-repo gate.** All GRUVAX-side phases (2–5) follow the walking skeleton; phase 2 cannot start until discogsography phase 1 ships `app_tokens` + catalog-number exposure.
3. **The 9 SPIDR-deferred v1.0 requirements** (SRCH-09, OFF-01..04, PRIV-01..04) are NOT pulled in by the spec but are natural v2.0 fits — surface this question explicitly in the roadmap kickoff.
4. **No new constraints contradict v1.0 NFRs.** The 200 ms SLO, p95 ≤ 50 ms /api/locate, offline resilience, and 3d/14d staleness thresholds all carry over verbatim.
5. **Profile + device migration** (REQ-profile-id-migration) is the highest-risk implementation item — touches most v1 tables, needs Alembic upgrade↔downgrade round-trip (existing v1.0 CI invariant).

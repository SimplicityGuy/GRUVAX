## Conflict Detection Report

### BLOCKERS (0)

No blockers detected. No LOCKED-vs-LOCKED contradictions; the v2.0 spec is `locked: false` per its classification (it uses "Locked Decisions" as internal design-phase language, not as GSD-locked ADRs). No cross-ref cycles (the only ingested doc has zero cross-refs). No UNKNOWN-confidence-low classifications.

### WARNINGS (1)

[WARNING] Phase 9 housekeeping scope already absorbed by v1.0 close
  Found: docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md (§ Phase 9) lists Phase 9 as "v1.x — done now, separate from v2.0" with these items: structlog migration, env-driven log level, GitHub workflows (test/code-quality/security/build + cleanup-cache + cleanup-images), `.github/dependabot.yml`, `.pre-commit-config.yaml`, `scripts/update-project.sh` adapted from discogsography, docs refresh removing `lux`/`nox` references, and the 64-ruff-error lint debt.
  Impact: .planning/MILESTONES.md records Phase 9 ("Tooling and Docs Hardening") as shipped at v1.0 close (2026-05-26): "Migrated to structlog (preserving the Phase 8 log ring buffer); env-driven log level; GitHub Actions tooling adapted from discogsography (lint/type/test + cleanup-cache + cleanup-images); dependabot; pre-commit hooks; `update-project.sh`; Phase 1–8 docs refresh stripping `lux`/`nox` references." However, user-memory `project_tooling_alignment_handoff` cites an in-flight branch `chore/align-discogsography-tooling` at commit `0381f76` with 83 ruff errors remaining and "1706-line update-project.sh adaptation still to do." The synthesizer cannot determine from the manifest alone whether MILESTONES.md is accurate (Phase 9 truly closed) or whether residual work spilled past v1.0 close.
  → Reconcile before routing v2.0: (a) confirm `chore/align-discogsography-tooling` branch landed on main before MILESTONES.md Phase 9 entry was written, or (b) carve a v1.x housekeeping wrap-up phase (separate from v2.0) for the residual lint-debt + `update-project.sh` adaptation. The v2.0 milestone scope itself is unaffected by this reconciliation — it only matters for whether REQ-structlog-migration / REQ-update-project-script / REQ-lint-debt-pass go on the v2.0 roadmap or are confirmed already-shipped.

### INFO (5)

[INFO] Auto-resolved: v2.0 milestone supersedes v1.0 `gruvax.v_collection` contact-surface decision
  Note: docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md (Locked Decisions D6 + D7, § What is retired) retires the `gruvax.v_collection` view and the read-only Postgres grant in favor of the discogsography HTTP API. v1.0's `.planning/PROJECT.md` (Key Decisions row "Dedicated `gruvax` schema in the same Postgres instance, reads via `gruvax.v_collection` view") and v1.0's `.planning/MILESTONES.md` (Key Decisions row "`gruvax.v_collection` view as the single contact surface with discogsography") both call this an intentionally v1.0-scoped decision marked ✓ Good. This is a milestone-boundary scope expansion (single-collection → multi-user collections), not a contradiction. Tagged `supersedes-on-v2-milestone` in `.planning/intel/decisions.md` (D6, D7). v1.0 decision remains correct for its scope; v2.0 changes the scope.

[INFO] Auto-resolved: v2.0 milestone extends v1.0 single-PIN / single-collection identity model
  Note: docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md (Locked Decisions D3) introduces "collection profiles" managed by the existing single-PIN owner. v1.0's `.planning/PROJECT.md` Constraints + Key Decisions ("Single PIN (Argon2id-hashed) gates admin actions … No multi-user concerns in v1") explicitly scopes single-user to v1. v2.0 preserves the single-PIN admin entry point and layers a profile-manager UI on top — there is no new account system, and the discogsography-side multi-user concept is the *authorization* mechanism, not a second GRUVAX account system. Milestone-boundary scope expansion, not a contradiction. Captured in `.planning/intel/decisions.md` D3.

[INFO] Auto-resolved: v2.0 milestone redefines staleness without contradicting v1.0 Phase 8
  Note: docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md (§ Collection sync-and-cache) redefines sync staleness as `now - profiles.last_sync_at` per profile, replacing v1's `max(v_collection.synced_at)`. v1.0 Phase 8 staleness banner thresholds (3 days / 14 days) carry over verbatim. This is a refactor of the source-of-truth signal, not a contradiction of the UX contract. Captured in `.planning/intel/constraints.md` CON-staleness-redefinition.

[INFO] Single-doc ingest: no LOCKED-vs-LOCKED check applicable
  Note: Only one source doc was classified (manifest-declared SPEC at `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md`). All seven internally-labeled "Locked Decisions" (D1–D7) live inside the same SPEC at the same precedence and do not conflict with each other. No cross-doc precedence resolution was needed.

[INFO] Open risk surfaced for downstream roadmapper attention (not a doc conflict)
  Note: docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md flags catalog-number exposure on discogsography's collection API as the HIGH-severity unknown (§ discogsography-Side Design "⚠ Catalog-number exposure"; § Risks #1). Position estimation is impossible without it. This is not a doc-conflict-engine conflict — it's an external dependency / verification task — but the roadmapper should ensure REQ-catalog-number-exposure is scheduled as a discogsography-Phase-1 prerequisite that gates the GRUVAX walking skeleton (v2 phase 2).

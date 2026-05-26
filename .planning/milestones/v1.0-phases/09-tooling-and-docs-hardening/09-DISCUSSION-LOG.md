# Phase 9: Tooling and docs hardening - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-25
**Phase:** 09-tooling-and-docs-hardening
**Areas discussed:** CI architecture & frontend coverage, Image publishing & cleanup-images, Lint-debt disposition, Docs refresh & host genericization

---

## CI architecture & frontend coverage

### CI wiring

| Option | Description | Selected |
|--------|-------------|----------|
| Independent files, direct triggers | Each of the 6 workflows triggers on its own events; no orchestrator/change-detection/matrix. Right-sized for one service. | |
| discogsography-style orchestration | Top-level workflow `workflow_call`s code-quality → test → build with gating (code-quality must pass first). Max sibling fidelity. | ✓ |
| Minimal: extend ci.yml + add cleanups | Keep single ci.yml, only add missing standalone workflows. Least churn. | |

**User's choice:** discogsography-style orchestration
**Notes:** Owner wants maximum sibling fidelity with discogsography. The six named workflows become separate files; the existing flat ci.yml is superseded but its hard gates (Alembic round-trip, benchmark SLO) must be preserved in the new `test` workflow.

### Frontend coverage

| Option | Description | Selected |
|--------|-------------|----------|
| Full coverage | code-quality runs eslint + prettier --check + tsc --noEmit; build builds the SPA; frontend tests in test. First-class gated surface. | ✓ |
| Build-only | CI builds the SPA but no eslint/prettier/tsc gates. | |
| Backend + infra only | Frontend entirely local/pre-commit; CI = Python + Docker + Alembic + benchmark. | |

**User's choice:** Full coverage
**Notes:** Frontend (`frontend/`, eslint already configured) is treated like the backend. May surface new failures — ties into the lint-debt decision (clean now).

---

## Image publishing & cleanup-images

### Publish to GHCR?

| Option | Description | Selected |
|--------|-------------|----------|
| Publish to GHCR | build pushes SHA+latest to ghcr.io on push-to-main; cleanup-images prunes on schedule; host can pull. Both workflows do real work. | ✓ |
| Build-validate only, no publish | build just proves `docker compose build` succeeds; cleanup-images dropped/dormant. Keeps local-build deploy. | |
| Build-validate now, publish later | build validates only; cleanup-images brought in disabled; defer GHCR to a later trigger. | |

**User's choice:** Publish to GHCR
**Notes:** Makes build + cleanup-images meaningful, matching the sibling-fidelity choice. Image path likely `ghcr.io/simplicityguy/gruvax-api` (planner confirms from remote).

### Deploy model

| Option | Description | Selected |
|--------|-------------|----------|
| Keep build-based deploy | compose stays `gruvax-api:local` + build context; GHCR is publish-only. Deploy unchanged; docs stay docs-only. | |
| Switch to pull-based deploy | compose references the ghcr image; deploy = `compose pull && up`; compose.override keeps local build for dev. Reproducible immutable deploys; changes compose.yaml + runbook. | ✓ |

**User's choice:** Switch to pull-based deploy
**Notes:** This is the one live-artifact change in the phase — ripples into compose.yaml, compose.override.yaml, justfile, and the runbook docs.

---

## Lint-debt disposition

| Option | Description | Selected |
|--------|-------------|----------|
| Clean it all now | Fix 64 ruff errors + new bandit/hadolint/actionlint/yamllint/shellcheck/eslint findings; drop every continue-on-error → true hard gate. Larger diff. | ✓ |
| Hybrid: core hard, infra advisory | ruff/mypy/eslint/tsc hard now; new infra linters advisory for one release with tracked follow-up. | |
| Keep advisory, track follow-up | Land tooling with continue-on-error where it fails today; file a dedicated lint-debt task. Smallest diff. | |

**User's choice:** Clean it all now
**Notes:** Consistent with the gating-orchestration choice — a gate allowed to fail isn't a gate. Planner should isolate the cleanup into its own wave/plan since it's potentially the largest, and is independent of the workflow YAML.

---

## Docs refresh & host genericization

### Docs form

| Option | Description | Selected |
|--------|-------------|----------|
| ARCHITECTURE.md + refresh README/CLAUDE | New user-facing docs/ARCHITECTURE.md (final Phase 1-8 design) + refresh README + CLAUDE Architecture section. Fills the "not yet mapped" gap; seeds v2.0. | ✓ |
| Refresh existing docs in place only | Update README + CLAUDE + runbook to match reality; no new doc. Lightest. | |
| ADR set + refresh | Retroactive ADRs in docs/adr/ for key decisions + in-place refreshes. Most ceremony. | |

**User's choice:** ARCHITECTURE.md + refresh README/CLAUDE
**Notes:** CLAUDE.md "Architecture" currently says "not yet mapped"; v2.0 milestone next — a consolidated architecture doc fills the gap. Diagrams in Mermaid.

### Host genericization

| Option | Description | Selected |
|--------|-------------|----------|
| Generic prose + neutral placeholder | "the deployment host" in prose; your-server.local / `<host>` for concrete examples; no new runtime config. | ✓ |
| Documented host variable convention | Introduce a documented ${GRUVAX_HOST}/DEPLOY_HOST used across docs + compose comments. | |
| Prose-only, no placeholder | Rewrite to "the deployment host"; use localhost/omit where a hostname is unavoidable. | |

**User's choice:** Generic prose + neutral placeholder
**Notes:** `lux` appears in CLAUDE.md ×4, README ×2, compose.yaml ×4, runbook ×1. `nox` appears nowhere — that strip is a confirmed no-op. Planner must check whether any `lux` in compose.yaml is load-bearing (alias/extra_hosts) vs. comments before editing.

---

## Claude's Discretion

Locked to "mirror discogsography, right-sized for a single service" — no discussion requested:
- **structlog migration** — processor-chain fidelity (ref disco `common/config.py`); hard constraint = preserve the `LogRingHandler`→deque on `app.state.log_ring_buffer` that `/admin/diagnostics` reads.
- **Env-driven log level** — extend existing `LOG_LEVEL`.
- **dependabot** — pip + github-actions + docker + npm/frontend; weekly Monday, grouped; drop the 8-service fan-out and cargo.
- **pre-commit hook set** — adapt disco's, drop Rust cargo hooks, add frontend (eslint/prettier), frozen revs at latest.
- **cleanup-cache** — mechanical adapt.
- **scripts/update-project.sh** — specialize down to one service; justfile-delegating.
- **security workflow** — right-sized for one Python service + frontend.

## Deferred Ideas

- **v2.0 multi-user collections** — next milestone; Phase 9 clears the runway.
- **mdformat pre-commit hook** — disco disabled it (CI/local inconsistency); skip in GRUVAX.
- **External metrics/APM** — out by footprint constraint (unchanged from Phase 8).
- *(Recorded as considered-and-rejected: "keep lint advisory + dedicated cleanup phase" — D-06 cleans now instead.)*
</content>

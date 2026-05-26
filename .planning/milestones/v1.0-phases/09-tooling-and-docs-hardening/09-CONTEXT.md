# Phase 9: Tooling and docs hardening - Context

**Gathered:** 2026-05-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Close out **v1.x developer-experience / tooling debt** before the v2.0 multi-user
milestone. **No product behavior changes** — this phase touches logging plumbing,
CI/CD, repo hygiene tooling, and docs only. The Core Value flow and every Phase 1–8
feature must behave identically after this phase.

**In scope (7 items, from ROADMAP.md §"Phase 9"):**
1. **structlog migration** — replace the stdlib `JsonFormatter` / `LogRingHandler`
   wiring (`src/gruvax/logging_config.py`, Phase 8) with `structlog`, **preserving the
   in-memory log ring buffer** (`deque` on `app.state.log_ring_buffer`) that
   `/admin/diagnostics` reads.
2. **Env-driven log level** — ensure debug/log level is settable via env var (extends
   the existing `LOG_LEVEL` already wired in `settings.py` + `compose.yaml`).
3. **GitHub Actions workflows** adapted from `discogsography/.github/workflows/`:
   `test`, `code-quality`, `security`, `build`, **`cleanup-cache`**, **`cleanup-images`**.
4. **dependabot** — adapt `discogsography/.github/dependabot.yml` (multi-ecosystem,
   grouped, weekly).
5. **pre-commit** — adapt `discogsography/.pre-commit-config.yaml`.
6. **`scripts/update-project.sh`** — adapt from discogsography (justfile-delegating),
   specialized for GRUVAX.
7. **Docs refresh** — capture the final Phase 1–8 design and **strip host names**
   (`lux`/`nox`) from docs/CLAUDE.md.

**Adaptation principle (applies to every item):** discogsography is an **8-service
monorepo** (Rust extractor, Neo4j, RabbitMQ, npm, GHCR-published images, matrix builds,
change-detection, `workflow_call` orchestration, sub-project listing). GRUVAX is a
**single service** (`gruvax-api` + `mosquitto`). Adaptation means **right-sizing down** —
keep the patterns and file names, drop the monorepo machinery that doesn't apply.

**Out of scope (other phases / backlog):**
- Any v1 product behavior change (search, locate, admin, LED, realtime, observability
  semantics) — all locked from Phases 1–8.
- v2.0 multi-user collections (separate milestone; see the v2 design doc in refs).
- Real LED firmware (hardware milestone).
- New external metrics/APM stack (footprint constraint — Phase 8 chose in-app diagnostics).
</domain>

<decisions>
## Implementation Decisions

### CI architecture (Area 1)
- **D-01:** **discogsography-style orchestration.** A top-level workflow `workflow_call`s
  the stages in sequence with gating — **`code-quality` must pass before `test` and
  `build` run** (mirrors disco's `code-quality.yml` → `test`/`build` dependency). The
  scope's six named workflows (`test`, `code-quality`, `security`, `build`,
  `cleanup-cache`, `cleanup-images`) become **separate files** as named, not one flat
  `ci.yml`. The existing `.github/workflows/ci.yml` (Phase 8) is **superseded/replaced** by
  this structure — its hard gates (Alembic round-trip OBS-03, benchmark SLO SC5) must be
  preserved inside the new `test` workflow, not lost.
- **D-02:** **`code-quality` runs `pre-commit run --all-files`** as the single source of
  truth (mirrors disco caching pre-commit), rather than duplicating ruff/mypy/eslint as
  separate hand-written steps. *(Flag at plan time if a split is preferred for clearer
  per-tool annotations.)*
- **D-03:** **Full frontend coverage.** The React/Vite frontend (`frontend/`) is a
  first-class gated surface: `code-quality` runs **eslint + prettier `--check` + `tsc
  --noEmit`**; the `build` workflow builds the SPA; any frontend tests run under `test`.
  Treated exactly like the backend.

### Image publishing & deploy (Area 2)
- **D-04:** **Publish to GHCR.** The `build` workflow **pushes a tagged `gruvax-api` image
  to `ghcr.io`** on push-to-main (SHA tag + `latest`). `cleanup-images` prunes
  old/untagged versions on a schedule (disco's `keep-n-tagged` / `older-than 30 days`
  pattern, `dataaxiom/ghcr-cleanup-action`). Both `build` and `cleanup-images` do real
  work — no ceremony. *(Planner: confirm the exact image path from the repo remote — likely
  `ghcr.io/simplicityguy/gruvax-api`, lowercased; disco's GHCR owner is `SimplicityGuy`.)*
- **D-05:** **Pull-based deploy.** `compose.yaml` switches from `image: gruvax-api:local`
  + build context to **`image: ghcr.io/simplicityguy/gruvax-api:latest`**; deploy becomes
  **`docker compose pull && up`**. A **`compose.override.yaml`** keeps the local `build:`
  context for dev so `just up`/`just build` still work locally. This is the one place
  Phase 9 changes a live deploy artifact — it ripples into the docs refresh (D-10) and the
  runbook. Planner verifies the override correctly shadows the registry image for dev.

### Lint-debt disposition (Area 3)
- **D-06:** **Clean it all now → honest hard gate.** Fix the **64 pre-existing ruff
  errors** (carried as `continue-on-error` in Phase 8 CI) AND resolve any **new findings**
  surfaced by the adopted infra linters (**bandit, hadolint, actionlint, yamllint,
  shellcheck**) and the frontend linters (**eslint, prettier, tsc**). **Drop every
  `continue-on-error`** so `code-quality` is a true blocking gate (consistent with the
  gating-orchestration choice D-01 — a gate allowed to fail is not a gate).
- **D-07:** **Planner isolates the cleanup.** The ruff/lint cleanup is potentially the
  **largest chunk** of the phase and is **independent** of the workflow YAML; carve it into
  its own wave/plan so it can land and be verified separately from the tooling scaffolding.
  mypy `--strict` and frontend `tsc`/build were reported clean as of Phase 7 — verify they
  still are after Phase 8 additions; ruff is the known debt.

### Docs refresh & host genericization (Area 4)
- **D-08:** **New user-facing `docs/ARCHITECTURE.md`** capturing the final Phase 1–8
  design: data model + `gruvax.v_collection` contract, the `/api/*` + `/api/admin/*`
  surface, SSE realtime, the **segment/cut-point boundary model** (Phase 5), the
  **LED-over-MQTT contract** (Phase 6), and observability (Phase 8). This is **distinct
  from** the planning-time `.planning/research/ARCHITECTURE.md`. Diagrams in **Mermaid**
  (project convention).
- **D-09:** **Refresh README + CLAUDE.md.** Update `README.md` and the CLAUDE.md
  "Architecture" section (currently *"Architecture not yet mapped"*) to point at
  `docs/ARCHITECTURE.md` and reflect final reality (endpoints, schema, deploy, tooling).
  Fills the gap and seeds the v2.0 milestone.
- **D-10:** **`lux` → generic prose + neutral placeholder.** Prose becomes "the
  deployment host" / "the home server"; concrete examples (kiosk URL, runbook commands)
  use a neutral placeholder like `your-server.local` or `<host>`. **No new runtime config
  introduced** (this is a docs phase). `nox` does **not appear anywhere** in the docs —
  that half of the strip is a **confirmed no-op**. Planner must check whether any `lux` in
  `compose.yaml` is **load-bearing** (network alias / `extra_hosts` / `container_name`)
  vs. just comments before editing — genericize comments freely, treat config carefully.
  Known `lux` sites: `CLAUDE.md` (×4), `README.md` (×2), `compose.yaml` (×4),
  `docs/runbook-fresh-host.md` (×1).

### Claude's Discretion (locked to "mirror discogsography, right-sized for one service")
These were explicitly delegated — no user discussion needed; adapt the disco source,
strip monorepo-only parts:
- **structlog config fidelity:** how closely to mirror disco's processor chain
  (`common/config.py`: `ProcessorFormatter`, `TimeStamper(iso,utc)`, `add_log_level`,
  `add_logger_name`, contextvars merge, `dict_tracebacks`, `JSONRenderer` with an
  orjson serializer). Researcher/planner pick a right-sized chain. **Hard constraint:**
  the **`LogRingHandler` → `deque` on `app.state.log_ring_buffer`** must keep working so
  `/admin/diagnostics` still tails recent logs; decide whether the ring stores the current
  flat `{ts, level, logger, msg}` shape or richer structlog event dicts (default: preserve
  the existing shape the diagnostics page already renders unless trivially richer).
- **dependabot ecosystems/dirs:** GRUVAX is single-dir → `pip` (`/`), `github-actions`
  (`/`), `docker` (Dockerfile), and `npm` (`/frontend`). Weekly Monday, grouped
  (production/development/security), `SimplicityGuy` assignee — mirror disco's conventions,
  drop the 8-service directory fan-out and the `cargo` ecosystem.
- **pre-commit hook set:** adapt disco's `.pre-commit-config.yaml` — keep
  pre-commit-hooks, check-jsonschema (workflows/actions), ruff + ruff-format, bandit
  (`-x tests -s B608`), hadolint, docker-compose-check, actionlint, yamllint, shellcheck,
  shfmt, and the **local mypy hook**. **Drop the Rust `cargo-fmt`/`cargo-clippy` hooks**
  (no Rust). Add frontend hooks (eslint/prettier) per D-03. Use **frozen/pinned revs at
  current latest** (per "always latest versions" — see memory).
- **`cleanup-cache`:** mechanical adapt (PR-close trigger, `gh cache delete` loop).
- **`scripts/update-project.sh`:** disco's is 58 KB and monorepo/sub-project-aware.
  Specialize **down** to GRUVAX: update uv deps + lockfile, `pre-commit autoupdate`,
  update `frontend/` npm deps, delegate to `justfile` recipes. Drop sub-project iteration.
- **`security` workflow:** adapt disco's `security.yml` right-sized (bandit / dependency
  scan / etc.) for a single Python service + frontend.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & roadmap (the locked acceptance spec for this phase)
- `.planning/ROADMAP.md` §"Phase 9: Tooling and docs hardening" — the 7 scope items and
  the discogsography-adaptation notes (incl. the 64-ruff-error advisory note).
- `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` §"Phase 9
  (v1.x — done now, separate from v2.0)" — the canonical Phase 9 scope list and the
  lux/nox strip directive; also the v2.0 milestone this phase clears the runway for.
- `.planning/PROJECT.md` — constraints that still bind: home-LAN only / no public
  exposure, footprint (~$80–150, no heavyweight services), **repo hygiene** (collection
  CSV + `background/` never committed → CI/tooling must never touch them).

### discogsography adaptation sources (the templates to right-size, in `/Users/Robert/Code/public/discogsography/`)
- `discogsography/.github/workflows/` — `test.yml`, `code-quality.yml` (note: `on:
  workflow_call`, gates the rest), `security.yml`, `build.yml` (GHCR publish; `REGISTRY:
  ghcr.io`, `packages: write`), `cleanup-cache.yml`, `cleanup-images.yml`
  (`dataaxiom/ghcr-cleanup-action`, keep-n-tagged 2, older-than 30d). **Strip:**
  change-detection, matrix-over-8-services, `list-sub-projects.yml`, Rust/Neo4j/RabbitMQ
  bits.
- `discogsography/.github/dependabot.yml` — multi-ecosystem grouped weekly pattern
  (right-size dirs/ecosystems per D's discretion note).
- `discogsography/.pre-commit-config.yaml` — the hook set to adapt (drop cargo hooks).
- `discogsography/scripts/update-project.sh` — the justfile-delegating updater to
  specialize down.
- `discogsography/common/config.py` (≈lines 330–444) — the **structlog configuration
  reference** (processor chain, ProcessorFormatter, JSONRenderer, LOG_LEVEL handling).

### Existing GRUVAX code to extend / replace (NOT rebuild from zero)
- `src/gruvax/logging_config.py` — current `JsonFormatter` + `LogRingHandler` to **replace
  with structlog** while preserving the ring buffer (D-01 structlog / Claude's discretion).
- `src/gruvax/app.py` — lifespan logging init + where the ring buffer is wired to
  `app.state.log_ring_buffer`.
- `src/gruvax/settings.py` — existing `LOG_LEVEL` config (extend for D-02 env-driven level).
- `src/gruvax/api/admin/diagnostics.py` — the consumer of the log ring buffer; its read
  shape is the **contract the structlog migration must not break**.
- `.github/workflows/ci.yml` — the Phase 8 single-file CI to **supersede**; preserve its
  hard gates (Alembic round-trip lines 96–103, benchmark SLO lines 108–117) into the new
  `test` workflow.
- `compose.yaml` — flips to the GHCR image + needs a `compose.override.yaml` sibling (D-05);
  has `lux` refs to genericize (D-10).
- `justfile` — recipes `update-project.sh` delegates to; `build`/`up`/`build-version`/`demo`
  recipes interact with the deploy-model change (D-05).
- `scripts/` — existing dir (`check_benchmark.py`, `run_all_algorithms.py`, `set_pin.py`)
  where `update-project.sh` lands.
- `pyproject.toml` / `uv.lock` — add `structlog` (+ orjson if chosen) as deps; the ruff
  config that the 64-error cleanup (D-06) must satisfy.

### Docs to write / refresh (Area 4)
- `docs/ARCHITECTURE.md` — **new** (D-08).
- `README.md`, `CLAUDE.md` ("Architecture" + "Technology Stack" sections), and
  `docs/runbook-fresh-host.md` — refresh + lux-strip (D-09, D-10).
- `.planning/codebase/CONVENTIONS.md` — project conventions (Mermaid diagrams, vanilla-DOM
  frontend, psycopg `%s`, routers imported inside `create_app()`) the new docs must reflect.

### Conventions & memory (binding behaviors)
- **Mermaid-only diagrams** in all docs (project convention + user memory).
- **Always latest versions** — pin pre-commit revs, action SHAs, tool versions to current
  latest; overrides STACK.md/CLAUDE.md version pins (user memory).
- **Worktrees + parallel executors** — execute-phase uses git-worktree isolation +
  within-wave parallel dispatch (user memory; relevant since D-07 isolates the lint cleanup
  into its own wave — mind worktree base-drift / deletion-cleanup caveats in memory).
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`src/gruvax/logging_config.py`** — `JsonFormatter` + `LogRingHandler` document the exact
  ring-buffer contract (`{ts: float, level, logger, msg}` dict on a `deque(maxlen=200)`
  scoped to the `gruvax` logger, NOT root, so third-party records can't leak secrets to the
  admin UI). structlog must reproduce this scoping + shape.
- **`.github/workflows/ci.yml`** (Phase 8) — already has working: uv setup, Postgres 18
  service, synthetic-seed step, Alembic round-trip, full pytest, benchmark SLO gate via
  `scripts/check_benchmark.py`. Reuse these steps verbatim inside the new `test` workflow.
- **`justfile`** — `test`, `lint`, `lint-fix`, `typecheck`, `migrate-roundtrip`,
  `build`, `up`, `demo`, `build-version` recipes; `update-project.sh` should delegate here
  (disco pattern).
- **`scripts/check_benchmark.py`** — the SLO gate the new `test` workflow must keep calling.

### Established Patterns
- **CI uses the synthetic dataset only** (`fixtures/synth_collection.sql`) — never the real
  collection CSV or `background/` (repo-hygiene constraint). All new workflows inherit this.
- **`LOG_LEVEL` already plumbed** through `settings.py` + `compose.yaml` env — D-02 extends,
  doesn't introduce.
- **Python 3.14 / Postgres 18 / latest images** in CI (per "always latest"); existing
  `ci.yml` uses `PYTHON_VERSION: "3.14"`, `postgres:18`, `eclipse-mosquitto:2.1.2-alpine`.
- **`/admin/diagnostics` reads in-memory ring buffers** (log + slow-query, both reset on
  restart, D-08/D-12 from Phase 8) — the structlog migration is invisible to the UI iff the
  ring shape is preserved.
- **GHCR owner is `SimplicityGuy`** (from disco's dependabot assignee + cleanup-images
  `owner: github.repository_owner`); git user `robert@simplicityguy.com`.

### Integration Points
- **Logging:** `app.py` lifespan ↔ `logging_config.py` (structlog config) ↔
  `app.state.log_ring_buffer` ↔ `api/admin/diagnostics.py` (reader). Keep the seam stable.
- **CI:** new orchestrator `workflow_call`s `code-quality` (gate) → `test`/`build`;
  `code-quality` runs `pre-commit run --all-files`; `build` → GHCR; `cleanup-images`
  prunes GHCR; `cleanup-cache` on PR-close.
- **Deploy:** `compose.yaml` (GHCR image) + `compose.override.yaml` (local build) +
  `justfile` recipes + `docs/runbook-fresh-host.md` all move together (D-05/D-10).
- **Repo root:** new `.pre-commit-config.yaml`, `.github/dependabot.yml`,
  `scripts/update-project.sh`, `docs/ARCHITECTURE.md`; supersede `.github/workflows/ci.yml`.
</code_context>

<specifics>
## Specific Ideas

- **Honest green CI is the bar.** Because `code-quality` *gates* `test`/`build` (D-01), no
  `continue-on-error` survives — the 64 ruff errors + all new infra-linter findings get
  fixed (D-06). If that proves huge, it's its own wave (D-07), but the phase does not ship
  with a cosmetic gate.
- **Right-size, don't transplant.** Every discogsography artifact is adapted *down* for one
  service: no matrix, no sub-project listing, no cargo/Neo4j/RabbitMQ. Keep the file names
  and the patterns so the two repos feel like siblings.
- **The ring buffer is the one thing the logging migration must not break.** structlog is a
  means; `/admin/diagnostics` tailing recent logs is the observable behavior that must
  survive byte-compatible.
- **Pull-based deploy is the only live-artifact change.** Treat `compose.yaml` /
  `compose.override.yaml` / runbook edits with care; verify the override shadows the
  registry image for local dev before calling it done.
- **`nox` strip is a no-op** — it appears nowhere; don't invent references to remove.
</specifics>

<deferred>
## Deferred Ideas

- **v2.0 multi-user collections** — entire next milestone (discogsography-API-backed
  per-user collections); Phase 9 only clears the v1.x runway. See the v2 design doc.
- **Dedicated lint-debt phase** — *not* deferred: D-06 cleans it now. (Recorded so it's
  clear the "keep advisory + follow-up" option was considered and rejected.)
- **Markdown formatting hook (`mdformat`)** — disco disabled it for CI/local inconsistency;
  GRUVAX should skip it too unless a clean setup is found. Not adopting in this phase.
- **External metrics/APM** — out by footprint constraint (Phase 8 decision); unchanged.

No scope-creep ideas were raised — discussion stayed within the tooling/docs domain.
</deferred>

---

*Phase: 09-tooling-and-docs-hardening*
*Context gathered: 2026-05-25*
</content>
</invoke>

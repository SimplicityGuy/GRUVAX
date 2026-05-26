# Phase 9: Tooling and Docs Hardening — Pattern Map

**Mapped:** 2026-05-25
**Files analyzed:** 21 new/modified files
**Analogs found:** 21 / 21

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/gruvax/logging_config.py` | utility | event-driven | `src/gruvax/logging_config.py` (self) + `discogsography/common/config.py` | exact (self-rewrite) |
| `src/gruvax/app.py` | config | event-driven | `src/gruvax/app.py` (self, lifespan section) | exact (targeted edit) |
| `src/gruvax/settings.py` | config | request-response | `src/gruvax/settings.py` (self, extend LOG_LEVEL) | exact (targeted edit) |
| `pyproject.toml` | config | batch | `pyproject.toml` (self) | exact (add deps + ruff fix) |
| `.github/workflows/build.yml` (orchestrator) | config | batch | `discogsography/.github/workflows/build.yml` | role-match (right-size down) |
| `.github/workflows/code-quality.yml` | config | batch | `discogsography/.github/workflows/code-quality.yml` | role-match (right-size down) |
| `.github/workflows/test.yml` | config | batch | `.github/workflows/ci.yml` (self, supersede) | exact (extract + preserve gates) |
| `.github/workflows/security.yml` | config | batch | `discogsography/.github/workflows/security.yml` | role-match (right-size down) |
| `.github/workflows/cleanup-cache.yml` | config | event-driven | `discogsography/.github/workflows/cleanup-cache.yml` | exact (mechanical adapt) |
| `.github/workflows/cleanup-images.yml` | config | batch | `discogsography/.github/workflows/cleanup-images.yml` | role-match (right-size down) |
| `.github/dependabot.yml` | config | batch | `discogsography/.github/dependabot.yml` | role-match (right-size dir fan-out) |
| `.pre-commit-config.yaml` | config | batch | `discogsography/.pre-commit-config.yaml` (via RESEARCH.md Pattern 6) | role-match (drop cargo, add frontend) |
| `compose.yaml` | config | request-response | `compose.yaml` (self, targeted edits) | exact (flip image + genericize comments) |
| `compose.override.yaml` | config | request-response | `compose.yaml` (self, new sibling) | role-match (Docker Compose override pattern) |
| `scripts/update-project.sh` | utility | batch | `discogsography/scripts/update-project.sh` | role-match (right-size down) |
| `docs/ARCHITECTURE.md` | config | n/a (docs) | `docs/runbook-fresh-host.md` (structure) + CONVENTIONS.md (Mermaid rule) | partial-match (same Markdown + Mermaid convention) |
| `README.md` | config | n/a (docs) | `README.md` (self, refresh) | exact (targeted edits) |
| `CLAUDE.md` | config | n/a (docs) | `CLAUDE.md` (self, Architecture section) | exact (targeted section edit) |
| `docs/runbook-fresh-host.md` | config | n/a (docs) | `docs/runbook-fresh-host.md` (self, lux-strip) | exact (targeted prose edit) |
| `justfile` | config | batch | `justfile` (self, add recipe) | exact (add `lint-precommit`) |
| `.gitignore` | config | n/a | `.gitignore` (self, add compose.override.yaml) | exact (append one line) |

---

## Pattern Assignments

### `src/gruvax/logging_config.py` (utility, event-driven — full rewrite)

**Analog:** `src/gruvax/logging_config.py` (current implementation, the contract to preserve) + `discogsography/common/config.py` lines 330–444 (the processor chain template)

**Preserve contract from** `src/gruvax/logging_config.py` lines 59–91:
```python
class LogRingHandler(logging.Handler):
    def __init__(self, ring: deque[dict[str, Any]], level: int = logging.INFO) -> None:
        super().__init__(level)
        self._ring = ring

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._ring.append(
                {
                    "ts": record.created,      # float — unchanged
                    "level": record.levelname,  # str — unchanged
                    "logger": record.name,      # str — unchanged
                    "msg": record.getMessage(), # str — unchanged shape
                }
            )
        except Exception:
            self.handleError(record)
```

**New LogRingHandler pattern** (from RESEARCH.md Pattern 1, verified by live code test):
```python
# structlog-aware version: record.msg may be a dict (structlog-native) or str (stdlib foreign)
def emit(self, record: logging.LogRecord) -> None:
    try:
        if isinstance(record.msg, dict):
            msg = record.msg.get("event", "")   # structlog-native path
        else:
            msg = record.getMessage()            # stdlib foreign path
        self._ring.append({
            "ts": record.created,
            "level": record.levelname,
            "logger": record.name,
            "msg": msg,
        })
    except Exception:
        self.handleError(record)
```

**New configure_logging() function** (replaces JsonFormatter + per-handler setup):
```python
import logging
import orjson
import structlog
from collections import deque
from typing import Any

def _orjson_serializer(obj: Any, **_kw: Any) -> str:
    return orjson.dumps(obj).decode()

def configure_logging(log_level: str, ring: deque[dict[str, Any]]) -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.dict_tracebacks,
                structlog.processors.JSONRenderer(serializer=_orjson_serializer),
            ],
        )
    )

    logging.basicConfig(level=level, handlers=[console_handler], force=True)

    # Ring buffer scoped to gruvax logger ONLY — same security constraint as before (WR-02)
    logging.getLogger("gruvax").addHandler(LogRingHandler(ring, level=logging.INFO))

    # Same third-party suppression as before
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
```

**Critical scoping rule** (from `logging_config.py` docstring line 22-24 and `app.py` lines 95-100):
- `LogRingHandler` attaches to `logging.getLogger("gruvax")` — NEVER to the root logger
- This prevents third-party loggers (psycopg DSN in connection errors) from reaching admin UI

---

### `src/gruvax/app.py` (config, event-driven — targeted lifespan edit)

**Analog:** `src/gruvax/app.py` lines 85–100 (the section to replace)

**Current pattern to replace** (lines 85–100):
```python
# Current — replace this entire block
_log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
_root = logging.getLogger()
_root.setLevel(_log_level)
_json_handler = logging.StreamHandler()
_json_handler.setFormatter(JsonFormatter())
_root.handlers = [_json_handler]
_log_ring: deque[dict[str, Any]] = deque(maxlen=200)
app.state.log_ring_buffer = _log_ring
logging.getLogger("gruvax").addHandler(LogRingHandler(_log_ring, level=logging.INFO))
```

**New pattern** (calls configure_logging() from the new logging_config.py):
```python
# Replace the block above with:
_log_ring: deque[dict[str, Any]] = deque(maxlen=200)
app.state.log_ring_buffer = _log_ring
configure_logging(settings.LOG_LEVEL, _log_ring)
```

**Import change** (line 40 — replace old imports with new):
```python
# Remove:
from gruvax.logging_config import JsonFormatter, LogRingHandler
# Add:
from gruvax.logging_config import configure_logging
```

---

### `src/gruvax/settings.py` (config, request-response — no change needed)

**Analog:** `src/gruvax/settings.py` lines 47–49

`LOG_LEVEL` is already present and plumbed. D-02 extends it, does not rename it. The existing field definition is the final pattern:

```python
# settings.py lines 47-49 — already correct, no edit needed for D-02
LOG_LEVEL: str = "INFO"
```

The `configure_logging()` call in `app.py` reads `settings.LOG_LEVEL` — `LOG_LEVEL` is already settable via env var (`LOG_LEVEL=DEBUG docker compose up`). No schema change required.

---

### `pyproject.toml` (config, batch — add deps + ruff cleanup)

**Analog:** `pyproject.toml` lines 10–26 (dependencies block) and lines 65–77 (ruff config)

**Add to `[project].dependencies`** (lines 10–26):
```toml
"structlog>=25.5.0",
"orjson>=3.11.9",
```

**Ruff rule set to satisfy after D-06 cleanup** (pyproject.toml lines 69–71 — no config change, just fix violations):
```toml
[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "C4", "SIM", "RUF"]
ignore = ["E501"]
```

Auto-fixable with `uv run ruff check --fix --unsafe-fixes src/ tests/`; 21 errors require manual edits (see RESEARCH.md Pitfall 6 breakdown).

---

### `.github/workflows/build.yml` (orchestrator — new file, replaces `ci.yml`)

**Analog:** `discogsography/.github/workflows/build.yml` lines 1–30 (header + triggers + env) and lines 82–145 (workflow_call structure + aggregate-results)

**Trigger + env pattern** (from disco build.yml, right-sized — no schedule, no workflow_dispatch):
```yaml
name: Build

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  CI: true
  PYTHON_VERSION: "3.14"
  NODE_VERSION: "26"
  REGISTRY: ghcr.io

permissions:
  contents: read
  packages: write
```

**Orchestrator jobs pattern** (strip detect-changes, list-sub-projects, matrix; keep workflow_call fan-out):
```yaml
jobs:
  run-code-quality:
    uses: ./.github/workflows/code-quality.yml
    secrets: inherit

  run-tests:
    needs: [run-code-quality]
    uses: ./.github/workflows/test.yml
    secrets: inherit

  run-security:
    needs: [run-code-quality]
    uses: ./.github/workflows/security.yml
    secrets: inherit
    permissions:
      contents: read
      security-events: write

  build:
    needs: [run-tests, run-security]
    runs-on: ubuntu-latest
    # ... GHCR push (see build step pattern below)

  aggregate-results:
    runs-on: ubuntu-latest
    needs: [run-code-quality, run-tests, run-security, build]
    if: always()
    # ... check all results
```

**GHCR image name lowercasing pattern** (from disco build.yml lines 207–209):
```yaml
- name: Set lowercase image name
  run: echo "IMAGE_NAME=$(echo '${{ github.repository }}' | tr '[:upper:]' '[:lower:]')" >> $GITHUB_ENV
```
Image path: `ghcr.io/${{ env.IMAGE_NAME }}` → `ghcr.io/simplicityguy/gruvax`

**Docker build+push pattern** (from disco build.yml lines 263–300, right-sized for single service):
```yaml
- name: Log in to GHCR
  if: github.event_name != 'pull_request'
  uses: docker/login-action@650006c6eb7dba73a995cc03b0b2d7f5ca915bee  # v4.2.0
  with:
    registry: ${{ env.REGISTRY }}
    username: ${{ github.actor }}
    password: ${{ secrets.GITHUB_TOKEN }}

- name: Extract Docker metadata
  id: meta
  uses: docker/metadata-action@80c7e94dd9b9319bd5eb7a0e0fe9291e23a2a2e9  # v6.1.0
  with:
    images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
    tags: |
      type=raw,value=latest,enable={{is_default_branch}}
      type=sha

- name: Set up Docker Buildx
  uses: docker/setup-buildx-action@d7f5e7f509e45cec5c76c4d5afdd7de93d0b3df5  # v4.1.0

- name: Build and push
  uses: docker/build-push-action@f9f3042f7e2789586610d6e8b85c8f03e5195baf  # v7.2.0
  with:
    context: .
    push: ${{ github.event_name != 'pull_request' }}
    tags: ${{ steps.meta.outputs.tags }}
    labels: ${{ steps.meta.outputs.labels }}
    build-args: |
      GIT_SHA=${{ github.sha }}
      BUILD_TIMESTAMP=${{ github.event.head_commit.timestamp }}
```

**Action SHAs to use** (from RESEARCH.md Standard Stack — verified 2026-05-25):
- `actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd` (v6.0.2)
- `astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b` (v8.1.0)
- `actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405` (v6.2.0)
- `actions/setup-node@48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e` (v6.4.0)
- `extractions/setup-just@53165ef7e734c5c07cb06b3c8e7b647c5aa16db3` (v4)

---

### `.github/workflows/code-quality.yml` (config, batch — new workflow_call file)

**Analog:** `discogsography/.github/workflows/code-quality.yml` lines 1–82

**Full structure pattern** (right-size: drop Rust toolchain, arkade/hadolint separate install, `install-all`; keep pre-commit cache):
```yaml
name: Code Quality

on:
  workflow_call:

env:
  CI: true
  PYTHON_VERSION: "3.14"
  NODE_VERSION: "26"

permissions:
  contents: read

jobs:
  code-quality:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Checkout repository
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd  # v6.0.2

      - name: Set up uv
        uses: astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b  # v8.1.0
        with:
          version: "latest"
          enable-cache: true

      - name: Set up Python
        uses: actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405  # v6.2.0
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Set up Node
        uses: actions/setup-node@48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e  # v6.4.0
        with:
          node-version: ${{ env.NODE_VERSION }}

      - name: Set up Just
        uses: extractions/setup-just@53165ef7e734c5c07cb06b3c8e7b647c5aa16db3  # v4
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}

      - name: Cache pre-commit
        uses: actions/cache@27d5ce7f107fe9357f9df03efb73ab90386fccae  # v5.0.5
        with:
          path: ~/.cache/pre-commit
          key: ${{ runner.os }}-pre-commit-v1-${{ hashFiles('.pre-commit-config.yaml') }}
          restore-keys: |
            ${{ runner.os }}-pre-commit-v1-

      - name: Install dependencies
        run: uv sync --frozen

      - name: Install frontend dependencies
        run: npm --prefix frontend install

      - name: Run pre-commit (all-files — single source of truth per D-02)
        run: uv run pre-commit run --all-files
```

**Key right-sizing decisions:**
- No `arkade` tool installer (hadolint is in pre-commit hooks)
- No Rust toolchain setup (no Rust in GRUVAX)
- No separate eslint/prettier/tsc steps (D-02: pre-commit is the sole gate)
- `workflow_call` trigger with no inputs (D-01)

---

### `.github/workflows/test.yml` (config, batch — new workflow_call file)

**Analog:** `.github/workflows/ci.yml` (self — extract and preserve ALL existing steps verbatim)

**Required trigger** (must have `on: workflow_call` per Pitfall 4):
```yaml
name: Test

on:
  workflow_call:
```

**Services block** (copy verbatim from `ci.yml` lines 38–52):
```yaml
services:
  postgres:
    image: postgres:18
    env:
      POSTGRES_USER: gruvax
      POSTGRES_PASSWORD: gruvax
      POSTGRES_DB: gruvax
    ports:
      - 5432:5432
    options: >-
      --health-cmd "pg_isready -U gruvax -d gruvax"
      --health-interval 5s
      --health-timeout 3s
      --health-retries 20
```

**Env block** (copy verbatim from `ci.yml` lines 53–58):
```yaml
env:
  DATABASE_URL: "postgresql+psycopg://gruvax:gruvax@localhost:5432/gruvax"
  OBSERVED_DISCOGSOGRAPHY_SCHEMA: "gruvax_dev"
  SESSION_SECRET: "ci-test-secret-not-real"
  LOG_LEVEL: "WARNING"
```

**Preserve OBS-03 Alembic round-trip gate verbatim** (ci.yml lines 96–103):
```yaml
- name: Alembic round-trip
  run: |
    uv run alembic upgrade head
    uv run alembic downgrade base
    uv run alembic upgrade head
```

**Preserve SC5 benchmark SLO gate verbatim** (ci.yml lines 108–117):
```yaml
- name: Benchmark SLO gate
  run: |
    uv run pytest \
      tests/unit/test_algorithm.py::test_locate_benchmark \
      tests/integration/test_search_benchmark.py::test_search_slo_benchmark \
      --benchmark-only --benchmark-json=benchmark.json -q
    uv run python scripts/check_benchmark.py benchmark.json
```

**Synthetic seed step** (ci.yml line 94 — copy verbatim):
```yaml
- name: Seed synthetic collection
  run: psql postgresql://gruvax:gruvax@localhost:5432/gruvax < fixtures/synth_collection.sql
```

**No `continue-on-error` on any step** (D-06 — drop the advisory pattern that was in Phase 8 ci.yml lines 81–90).

---

### `.github/workflows/security.yml` (config, batch — new workflow_call file)

**Analog:** `discogsography/.github/workflows/security.yml` lines 1–180 (right-size: drop rust-security job)

**Keep from disco security.yml:**
- `python-security` job (lines 21–49): pip-audit + bandit + osv-scanner
- `semgrep` job (lines 53–94): CE scan + nosemgrep filter + SARIF upload
- `secret-scanning` job (lines 140–156): TruffleHog
- `container-scanning` job (lines 157–180): trivy fs scan

**Drop from disco security.yml:**
- `rust-security` job (lines 96–139) — no Rust in GRUVAX

**Required trigger + permissions** (line 11–19 of disco security.yml):
```yaml
on:
  workflow_call:

permissions:
  contents: read
  security-events: write
```

**Replace `just install-all` with single-service equivalent:**
```yaml
- name: Install dependencies
  run: uv sync --frozen
```

---

### `.github/workflows/cleanup-cache.yml` (config, event-driven — mechanical adapt)

**Analog:** `discogsography/.github/workflows/cleanup-cache.yml` lines 1–37 (copy verbatim — no monorepo parts)

The cleanup-cache workflow has no monorepo dependencies. Copy it exactly. The `GH_REPO` and `BRANCH` env vars are generic GitHub context references that work identically in GRUVAX:

```yaml
name: Cleanup Cache

on:
  pull_request:
    types:
      - closed

concurrency:
  group: cleanup-cache-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  cleanup:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      actions: write
    steps:
      - name: Cleanup Cache
        run: |
          echo "Fetching list of cache keys"
          cacheKeysForPR=$(gh cache list --ref "$BRANCH" --limit 100 --json id --jq ".[].id")
          set +e
          echo "Deleting caches..."
          for cacheKey in $cacheKeysForPR
          do
              gh cache delete "$cacheKey"
          done
          echo "Done"
        env:
          GH_TOKEN: ${{ github.token }}
          GH_REPO: ${{ github.repository }}
          BRANCH: refs/pull/${{ github.event.pull_request.number }}/merge
```

---

### `.github/workflows/cleanup-images.yml` (config, batch — right-size)

**Analog:** `discogsography/.github/workflows/cleanup-images.yml` lines 1–42 (drop matrix + list-sub-projects)

**Right-sized single-service version** (drop `list-sub-projects` job, drop `strategy.matrix`, hardcode `package: gruvax`):
```yaml
name: Cleanup Docker Images

on:
  workflow_dispatch:
  schedule:
    - cron: "0 0 15 * *"   # monthly on the 15th

concurrency:
  group: cleanup-images-${{ github.ref }}
  cancel-in-progress: false

jobs:
  cleanup:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    permissions:
      packages: write
      contents: read
    steps:
      - name: Cleanup Docker Images
        uses: dataaxiom/ghcr-cleanup-action@374e2028c8fb93b7219f3771cd405fab95d3dec4  # v1.2.0
        with:
          delete-partial-images: true
          delete-untagged: true
          keep-n-tagged: 2
          older-than: 30 days
          token: ${{ secrets.GITHUB_TOKEN }}
          package: gruvax        # single package — no matrix
          owner: ${{ github.repository_owner }}
```

---

### `.github/dependabot.yml` (config, batch — right-size)

**Analog:** `discogsography/.github/dependabot.yml` lines 1–136 (right-size dirs + drop cargo)

**GRUVAX right-sized version** (RESEARCH.md Pattern 5 — verbatim, already correct):
```yaml
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule: { interval: "weekly", day: "monday", time: "09:00", timezone: "America/Los_Angeles" }
    commit-message: { prefix: "ci", include: "scope" }
    labels: ["dependencies", "ci"]
    assignees: ["SimplicityGuy"]
    groups:
      actions: { patterns: ["*"] }

  - package-ecosystem: "docker"
    directory: "/"      # single Dockerfile at repo root (not 8-service fan-out)
    schedule: { interval: "weekly", day: "monday", time: "09:00", timezone: "America/Los_Angeles" }
    commit-message: { prefix: "docker", include: "scope" }
    labels: ["dependencies", "docker"]
    assignees: ["SimplicityGuy"]

  - package-ecosystem: "npm"
    directory: "/frontend"
    schedule: { interval: "weekly", day: "monday", time: "09:00", timezone: "America/Los_Angeles" }
    commit-message: { prefix: "deps", include: "scope" }
    labels: ["dependencies", "javascript"]
    assignees: ["SimplicityGuy"]
    groups:
      npm-dependencies: { patterns: ["*"] }

  - package-ecosystem: "pip"
    directory: "/"      # single pyproject.toml at repo root
    schedule: { interval: "weekly", day: "monday", time: "09:00", timezone: "America/Los_Angeles" }
    commit-message: { prefix: "deps", prefix-development: "deps-dev", include: "scope" }
    labels: ["dependencies", "python"]
    assignees: ["SimplicityGuy"]
    groups:
      python-production: { dependency-type: "production", patterns: ["*"] }
      python-development: { dependency-type: "development", patterns: ["*"] }
      python-security: { applies-to: security-updates, patterns: ["*"] }
```

**Dropped from disco:** `cargo` ecosystem, `directories:` fan-out (8 services → single `/`).

---

### `.pre-commit-config.yaml` (config, batch — new file)

**Analog:** `discogsography/.pre-commit-config.yaml` (via RESEARCH.md Pattern 6 — fully worked out)

Use the exact content from RESEARCH.md Pattern 6 (lines 530–642). Key differences from disco:
- Drop `cargo-fmt` + `cargo-clippy` hooks (no Rust)
- `docker-compose-check` targets `files: ^compose\.yaml$` (not `docker-compose.yml`)
- Add local hooks: `mypy`, `eslint`, `prettier`, `tsc`
- All revs at current latest (verified SHAs in RESEARCH.md Standard Stack table)

**Local mypy hook pattern** (system language, not isolated venv):
```yaml
- repo: local
  hooks:
    - id: mypy
      name: mypy
      entry: uv run mypy
      language: system
      types: [python]
      pass_filenames: false
      args: ["--strict", "src/gruvax/"]
```

**Note:** `mdformat` is deliberately omitted (disco disabled it for CI/local inconsistency; GRUVAX skips entirely per RESEARCH.md).

---

### `compose.yaml` (config, request-response — targeted edits only)

**Analog:** `compose.yaml` (self — four targeted changes)

**Change 1: Flip image for the `api` service** (line 48):
```yaml
# Before:
image: gruvax-api:local

# After:
image: ghcr.io/simplicityguy/gruvax:latest
```

**Change 2: Remove `build:` block from `api` service** (lines 44–47):
```yaml
# Remove:
build:
  context: .
  dockerfile: Dockerfile
```
(Build block moves to `compose.override.yaml`.)

**Change 3: Genericize all four `lux` comment occurrences** (verified prose-only at lines 15, 35, 56, 101):
- Line 15: `"production on 'lux'"` → `"production on the deployment host"`
- Line 35: `"Postgres on 'lux' instead"` → `"Postgres on the deployment host instead"`
- Line 56: `"Postgres on lux"` → `"Postgres on the deployment host"`
- Line 101: `"To use lux instead"` → `"To use the deployment host instead"`

**No other changes** — `extra_hosts`, network aliases, `container_name`, and volume definitions are not affected.

---

### `compose.override.yaml` (config, request-response — new file)

**Analog:** `compose.yaml` (self — creates new sibling with local `build:` context)

**Full content** (from RESEARCH.md Pattern 4):
```yaml
# compose.override.yaml — local dev: shadows the GHCR image with a local build.
# Add to .gitignore — do NOT commit to the deployment host.
# To use: docker compose up --build (just up delegates here automatically).
services:
  api:
    build:
      context: .
      dockerfile: Dockerfile
    image: gruvax-api:local   # local tag for dev; overrides compose.yaml GHCR image
```

**Critical: add to `.gitignore`** (Pitfall 3 — if this file is present on the prod host, `docker compose up` auto-loads it and tries to build from source):
```
compose.override.yaml
```

Also commit a `compose.override.yaml.example` with the same content and a comment header explaining it is dev-only.

---

### `scripts/update-project.sh` (utility, batch — new file adapted from disco)

**Analog:** `discogsography/scripts/update-project.sh` lines 1–100 (header + arg-parsing pattern)

**GRUVAX right-sized skeleton** (from RESEARCH.md Pattern 7):
```bash
#!/usr/bin/env bash
set -euo pipefail
# Usage: ./scripts/update-project.sh [--dry-run] [--major] [--skip-tests]
# Delegates to just wherever possible (justfile is the single source of truth).

# Options from disco's interface — keep for parity:
DRY_RUN=false
MAJOR_UPGRADES=false
SKIP_TESTS=false

# Parse args (same pattern as disco lines 96–130)
while [[ $# -gt 0 ]]; do
  case $1 in
    --dry-run) DRY_RUN=true; shift ;;
    --major) MAJOR_UPGRADES=true; shift ;;
    --skip-tests) SKIP_TESTS=true; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# Python deps via uv
just install                 # ensure env is clean (uv sync --frozen)
uv lock --upgrade            # refresh uv.lock within existing floor constraints

# pre-commit hooks
uv run pre-commit autoupdate

# Frontend deps
npm --prefix frontend update

# Tests post-update (unless skipped)
if [[ "$SKIP_TESTS" != "true" ]]; then
  just test
fi

echo "Done. Review git diff for surprising version jumps."
```

**Drop from disco's script:** sub-project iteration, Rust cargo update, Python version rewriting, pyproject.toml floor synchronization, backup files.

**Must be executable:** `chmod +x scripts/update-project.sh`

---

### `docs/ARCHITECTURE.md` (docs — new file)

**Analog:** `docs/runbook-fresh-host.md` (Markdown structure convention) + CONVENTIONS.md (Mermaid-only diagrams rule)

**Structure pattern from `docs/runbook-fresh-host.md`:**
- Flat `#` title, no front matter
- `##` sections with clear single-topic headers
- Fenced code blocks for commands
- Tables for structured lists (volumes, endpoints)

**Mermaid convention** (CONVENTIONS.md line 19 — binding):
```markdown
Every diagram MUST use a ```mermaid block — never ASCII art or prose arrows.
```

**Content outline** (from RESEARCH.md docs/ARCHITECTURE.md section, lines 869–951):
1. Data Model: schemas, `gruvax.v_collection` contract, key tables
2. API Surface: public + admin endpoints (verified against current router registration)
3. Position Estimation: two-level interpolation, LocateResult shape
4. LED Contract: MQTT topics, payload shape, HighlightRegistry TTL
5. Realtime: SSE events, kiosk re-render behavior
6. Observability: /api/health subsystems, ring buffer semantics
7. Deploy: Compose services, GHCR image path (post-Phase 9), StaticFiles SPA

All diagrams from RESEARCH.md Architecture Patterns section (Mermaid flowcharts) go into this file.

---

### `README.md` (docs, targeted refresh — D-09 + D-10)

**Analog:** `README.md` lines 1–60 (self — preserve banner + badge + nav structure, update content)

**Preserve pattern** (lines 1–19):
```markdown
<div align="center">
<picture>...</picture>        # theme-aware banner (do not change)
[![License...](...)          # badges — update Python version badge to 3.14+
**Bold tagline**
</div>
<p align="center">
[nav links]
</p>
```

**Targeted changes:**
- Line 26: Remove `` `lux` `` reference → "the home server"
- Line 43 (Hardware table): `Home server (\`lux\`)` → `Deployment host`
- Line 50 (Stack): Update Python version string to 3.14
- Add a `## Architecture` section pointing at `docs/ARCHITECTURE.md`
- Update Stack section to reflect Phase 9 additions (structlog, orjson)

---

### `CLAUDE.md` (docs, targeted refresh — D-09)

**Analog:** `CLAUDE.md` itself — the `## Architecture` section (currently reads `"Architecture not yet mapped"`)

**Current placeholder to replace:**
```markdown
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
```

**New pattern** (single pointer, no duplication):
```markdown
## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the Phase 1–8 design:
data model, API surface, position estimation, LED contract, realtime, observability,
and deploy model.
```

**lux-strip changes** (4 occurrences in CLAUDE.md — prose only):
- Replace `` `lux` `` → "the deployment host" or `` `your-server.local` ``

---

### `docs/runbook-fresh-host.md` (docs, targeted refresh — D-10)

**Analog:** `docs/runbook-fresh-host.md` line 8 (self — one occurrence)

**Single targeted change** (line 8):
```markdown
# Before:
# GRUVAX Fresh-Host Bring-Up Runbook
This runbook covers the first-time deployment of the GRUVAX Docker Compose stack on a
fresh host (e.g. `lux`).

# After:
# GRUVAX Fresh-Host Bring-Up Runbook
This runbook covers the first-time deployment of the GRUVAX Docker Compose stack on a
fresh deployment host (e.g. `your-server.local`).
```

Also update the `docker compose ps` expected output (line 62) to show the GHCR image name post-Phase-9:
```
gruvax-api-1    ghcr.io/simplicityguy/gruvax:latest    Up (healthy)    0.0.0.0:8000->8000/tcp
```

---

### `justfile` (config, batch — add one recipe)

**Analog:** `justfile` lines 19–21 (the `lint` recipe pattern)

**New recipe to add** (recommended by RESEARCH.md Open Question 1):
```just
# Run pre-commit on all files (the code-quality gate's single source of truth)
lint-precommit:
    uv run pre-commit run --all-files
```

Add after existing `lint` and `lint-fix` recipes. Keep existing `lint` recipe unchanged for backwards compatibility.

---

### `.gitignore` (config — append one line)

**Analog:** `.gitignore` lines 223–240 (GRUVAX-specific section at bottom)

**Append to the GRUVAX-generated/runtime section**:
```
# compose.override.yaml is dev-only — never deploy to production host
compose.override.yaml
```

---

## Shared Patterns

### Authentication / Gating — No New Surface
**Source:** `src/gruvax/api/deps.py` (`require_admin` dependency)
**Apply to:** No new endpoints in Phase 9 — pattern unchanged.

### Logging Scope Constraint (Cross-cutting)
**Source:** `src/gruvax/logging_config.py` line 23 (docstring), `src/gruvax/app.py` lines 95–100
**Apply to:** All files that touch logging setup

The ring buffer handler attaches exclusively to `logging.getLogger("gruvax")`:
```python
logging.getLogger("gruvax").addHandler(LogRingHandler(_log_ring, level=logging.INFO))
# NEVER: logging.getLogger().addHandler(LogRingHandler(...))
```

### CI: No continue-on-error (Cross-cutting)
**Source:** `.github/workflows/ci.yml` lines 80–90 (the Phase 8 pattern to ELIMINATE)
**Apply to:** All new workflow files

Zero `continue-on-error: true` in any step. D-06 mandates an honest gate. The Phase 8 advisory pattern (ruff/mypy with `continue-on-error`) is removed once D-07 cleans the 69 ruff errors.

### CI: Synthetic Dataset Only (Cross-cutting)
**Source:** `.github/workflows/ci.yml` line 94 + header comment (lines 6–7)
**Apply to:** `test.yml` and any new workflow with a Postgres service

```yaml
# NEVER seed the real collection CSV or background/ in CI
- name: Seed synthetic collection
  run: psql postgresql://gruvax:gruvax@localhost:5432/gruvax < fixtures/synth_collection.sql
```

### Mermaid-Only Diagrams (Cross-cutting)
**Source:** `.planning/codebase/CONVENTIONS.md` line 19
**Apply to:** `docs/ARCHITECTURE.md` and any doc file with diagrams

All diagrams use ```` ```mermaid ```` blocks. No ASCII art, no prose arrows.

### workflow_call Trigger Pattern (Cross-cutting)
**Source:** `discogsography/.github/workflows/code-quality.yml` line 7 (the `on: workflow_call` pattern)
**Apply to:** `code-quality.yml`, `test.yml`, `security.yml`

Each called workflow MUST declare:
```yaml
on:
  workflow_call:
```
Without this, the orchestrator's `uses: ./.github/workflows/X.yml` call fails (Pitfall 4).

---

## No Analog Found

All files have a usable analog. No files are entirely novel:

| File | Role | Analog Quality | Notes |
|---|---|---|---|
| `.yamllint` | config | partial-match | Referenced by `yamllint` hook; content is a minimal config doc (see yamllint docs). No GRUVAX precedent — use disco's as template if it exists, else minimal strict config. |

---

## Metadata

**Analog search scope:** `/Users/Robert/Code/public/GRUVAX/` (all source) + `/Users/Robert/Code/public/discogsography/` (template repo)
**Files scanned:** 21 new/modified files classified; 15 analog files read
**Pattern extraction date:** 2026-05-25

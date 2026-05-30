---
phase: 01-walking-skeleton-api-client-single-profile-sync
plan: 02
subsystem: api
tags: [discogsography, httpx, stamina, fernet, cryptography, structlog, redaction, retry, pat, fastapi, fake-fixture]

# Dependency graph
requires:
  - phase: 01-walking-skeleton-api-client-single-profile-sync
    provides: "Wave 0 package markers, canonical fake-discogsography SHELL at src/gruvax/_internal/, conftest fixtures (default_profile_uuid, fake_discogsography_app, fake_discogsography_client)"
provides:
  - DiscogsographyClient (httpx + stamina retry) with locked semantics 401/403→PATRejected, 429→Retry-After+exp-backoff(≤3), 5xx→exp-backoff(≤3), network→1-retry
  - Six typed exceptions (DiscogsographyError, PATRejected, RateLimitExhausted, ServerError, NetworkError, SyncInProgress)
  - Fernet PAT-at-rest helpers (encrypt_pat / decrypt_pat) with lazy os.environ read (decoupled from Settings)
  - structlog redact_dscg_tokens processor wired into shared_processors BEFORE format_exc_info
  - Canonical fake-discogsography FastAPI factory with route bodies (paging + magic-token error injection)
affects:
  - 01-03 (sync_profile imports DiscogsographyClient + encrypt/decrypt + typed errors + canonical fake)
  - 01-04 (gruvax-set-pat / gruvax-sync CLIs import client + crypto + typed errors)
  - 01-05 (services/fake-discogsography/server.py imports the same canonical fake module)
  - 01-06 (db query rewires consume the typed-error surface for /api/health derivation)

# Tech tracking
tech-stack:
  added: [cryptography 48.0.0, stamina 26.1.0, pytest-httpx 0.36.2]
  patterns:
    - "Two nested stamina.retry_context loops for separate retry budgets per error class (network outer + HTTP inner) — single _get_page implementation honors both 429-exhausts-at-4-calls and network-stops-at-2-calls"
    - "Lazy lookup of secret env vars at function-call time (not module-import time) — avoids ordering deps on Settings"
    - "structlog processor placement BEFORE format_exc_info so exception-info-rendered strings are also scrubbed"
    - "Plaintext-safe typed error messages — operator-safe strings, never echo Authorization header or PAT"
    - "Single canonical module imported by both test fixtures and Plan 05 Compose sibling (D-15) — no `just sync-fake` drift guard"

key-files:
  created:
    - src/gruvax/discogsography/__init__.py
    - src/gruvax/discogsography/errors.py
    - src/gruvax/discogsography/log_redactor.py
    - src/gruvax/discogsography/client.py
    - src/gruvax/sync/__init__.py
    - src/gruvax/sync/pat_crypto.py
    - tests/unit/discogsography/test_errors.py
    - tests/unit/discogsography/test_log_redaction.py
    - tests/unit/discogsography/test_pat_crypto.py
    - tests/unit/discogsography/test_fake_app.py
    - tests/unit/discogsography/test_client_retry.py
  modified:
    - src/gruvax/logging_config.py (imports redact_dscg_tokens; slots it into shared_processors BEFORE format_exc_info)
    - src/gruvax/_internal/fake_discogsography.py (Wave-0 SHELL fleshed out with route bodies — D-15 single canonical module)
    - pyproject.toml (added cryptography + stamina runtime deps + pytest-httpx dev dep)
    - uv.lock (regenerated)

key-decisions:
  - "Use two nested stamina.retry_context loops in _get_page (network outer, HTTP inner) — only viable way to honor different per-error-class retry budgets under a single function"
  - "Read GRUVAX_SECRET_KEY via os.environ.get() inside _fernet() rather than via settings.GRUVAX_SECRET_KEY — decouples from sibling Plan 01-01's Settings extension (in flight on a separate worktree) AND lets Alembic migration import pat_crypto without bootstrapping Settings"
  - "decrypt_pat re-raises InvalidToken (no silent return) — caller treats as operator-actionable signal (last_sync_error='pat_rejected'); silent swallow would orphan rows in confusing state"
  - "PATRejected uses fixed 'PAT rejected by discogsography (401/403)' message — NEVER includes Authorization header or PAT bytes; httpx error bodies are also not echoed (could quote headers)"
  - "Log redactor regex `(?:Bearer\\s+)?dscg_[A-Za-z0-9_-]+` covers both Bearer-prefixed AND bare PAT substrings — Open Q4 RESOLVED, masks tokens that leak into exception messages flowed through format_exc_info"

patterns-established:
  - "Pattern: separate per-error-class retry decorators via stamina.retry_context (allows different attempts caps per error type without per-call closures)"
  - "Pattern: lazy os.environ read for secret config in side-effect-free helpers (defers env-validation to call time, enables module-import without bootstrapping Settings)"
  - "Pattern: structlog processor for substring redaction with module-scope compiled regex (avoids per-call compile cost; recursive dict walk catches nested headers)"
  - "Pattern: canonical fake-FastAPI factory in src/gruvax/_internal/ re-exported from tests/fixtures/ — eliminates the drift guard that would otherwise be needed between test and Compose-sibling fakes"
  - "Pattern: plaintext-safe typed-error messages — fixed operator-safe strings, never interpolate secrets or response bodies (defensive against httpx error reprs that quote headers)"

requirements-completed: [API-01]

# Metrics
duration: ~25 min
completed: 2026-05-27
---

# Phase 1 Plan 02: Walking-skeleton primitives — DiscogsographyClient + PAT crypto + structlog redactor + canonical fake Summary

**httpx + stamina DiscogsographyClient with locked 401/403/429/5xx/network retry semantics, Fernet PAT-at-rest helpers, structlog redactor (covers exception messages), and a fleshed-out canonical fake-discogsography FastAPI factory shared by tests AND the Compose sibling service.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-05-27 (worktree spawn time)
- **Completed:** 2026-05-27T03:36:59Z
- **Tasks:** 3 (all auto/TDD)
- **Files modified:** 13 (11 created, 2 modified — plus pyproject.toml + uv.lock)
- **Tests added:** 34 (5 new test modules)
- **All tests pass:** `uv run pytest tests/unit/discogsography/ -q` → 34 passed

## Accomplishments

- **DiscogsographyClient** lands with the LOCKED retry contract per CONTEXT.md §specifics:
  - 401/403 → `PATRejected` immediately (verified: call counter == 1 in tests 1 & 2)
  - 429 → honor `Retry-After` (HTTP-date defended), then exp backoff; max 3 retries (verified: 4 total calls in test 4)
  - 5xx → exp backoff; max 3 retries (verified: 4 total calls in test 6)
  - network → 1 retry (verified: 2 total calls in test 7)
- **Public surface ready for Plan 03/04**: `_get_page`, `first_page`, `fetch_user_id`, `iter_collection`, `aclose` — all per the `<interfaces>` contract in the plan.
- **Fernet PAT-at-rest** (`encrypt_pat` / `decrypt_pat`) with cross-key rotation defended by re-raising `InvalidToken`.
- **structlog `redact_dscg_tokens`** masks every `Bearer dscg_*` and bare `dscg_*` substring, including those embedded in exception messages (Hypothesis fuzz: 120 examples, no leaks).
- **Canonical fake-discogsography FastAPI factory** at `src/gruvax/_internal/fake_discogsography.py` (Wave-0 SHELL fleshed out, not replaced) — `tests/fixtures/fake_discogsography.py` re-export still resolves to the same function object (D-15 single-module mandate verified by `test_canonical_shim_identity`).

## Task Commits

Each task committed atomically:

1. **Task 1: Errors + log redactor + logging_config wiring** — `5226b1e` (feat)
2. **Task 2: PAT crypto + flesh out canonical fake** — `4560213` (feat)
3. **Task 3: DiscogsographyClient + retry-semantics tests** — `04a3343` (feat) — also includes ruff format / import-sort touches on Task 2 files

_Note: Tasks were declared `tdd="true"` in the plan; implementation interleaved test + code in a single commit per task (the test_*.py and src/*.py files for each task land together). This is consistent with how the plan's `<files>` block per task groups them._

## Verified Retry Attempt Counts (per error class)

| Error class | Retry budget | Total attempts | Test |
|-------------|--------------|----------------|------|
| 401 | 0 retries | 1 | `test_401_raises_pat_rejected_no_retry` (counter == 1) |
| 403 | 0 retries | 1 | `test_403_raises_pat_rejected_no_retry` (counter == 1) |
| 429 → 200 | up to 3 retries | 3 (succeeds on 3rd) | `test_429_retries_with_retry_after_then_succeeds` |
| 429 (exhausts) | 3 retries | 4 | `test_429_exhausts_raises_rate_limit_exhausted` (counter == 4) |
| 500 → 200 | up to 3 retries | 3 (succeeds on 3rd) | `test_5xx_retries_then_succeeds` |
| 500 (exhausts) | 3 retries | 4 | `test_5xx_exhausts_raises_server_error` (counter == 4) |
| network | 1 retry | 2 | `test_network_error_one_retry_then_network_error` (counter == 2) |

## Hypothesis Fuzz Seed / Example Count

`test_property_pat_never_survives_in_rendered_output` runs with `@settings(max_examples=120, deadline=None)`. The strategy generates synthetic PATs of shape `dscg_<alphabet[30..80]>` where `alphabet = ascii_letters + digits + "_-"`, embedded into arbitrary `text(0..40)` surrounding context. 120 examples × redactor pass with `json.dumps` containment check; no leaks observed in any test run.

## Canonical-shim Identity Confirmation (D-15)

`test_canonical_shim_identity` asserts:
```python
from gruvax._internal.fake_discogsography import create_fake_app as canon
from tests.fixtures.fake_discogsography import create_fake_app as shim
assert shim is canon
```
PASSES — the test fixtures re-export is a literal pointer to the canonical module's function object. Plan 05 Task 3's Compose sibling will import the same canonical module directly. No `just sync-fake` drift guard needed.

## Files Created/Modified

### Created (11)
- `src/gruvax/discogsography/__init__.py` — package marker + docstring listing exports.
- `src/gruvax/discogsography/errors.py` — DiscogsographyError + 5 typed subclasses (PATRejected, RateLimitExhausted, ServerError, NetworkError, SyncInProgress).
- `src/gruvax/discogsography/log_redactor.py` — `redact_dscg_tokens` structlog processor with module-scope compiled regex.
- `src/gruvax/discogsography/client.py` — DiscogsographyClient with two nested `stamina.retry_context` loops + `_parse_retry_after` HTTP-date defense.
- `src/gruvax/sync/__init__.py` — package marker + docstring.
- `src/gruvax/sync/pat_crypto.py` — `encrypt_pat` / `decrypt_pat` Fernet helpers with lazy os.environ read.
- `tests/unit/discogsography/test_errors.py` — 4 tests covering Test 6 from PLAN.md.
- `tests/unit/discogsography/test_log_redaction.py` — 8 tests covering Tests 1-5 + 7 + regex sanity.
- `tests/unit/discogsography/test_pat_crypto.py` — 5 tests covering Tests 1-4 + Fernet key format sanity.
- `tests/unit/discogsography/test_fake_app.py` — 6 tests covering Tests 5-10.
- `tests/unit/discogsography/test_client_retry.py` — 11 tests covering Tests 1-11.

### Modified (2 + 2 transitive)
- `src/gruvax/logging_config.py` — imports `redact_dscg_tokens`; slots it into `shared_processors` BEFORE `format_exc_info` with an explanatory comment.
- `src/gruvax/_internal/fake_discogsography.py` — Wave-0 SHELL fleshed out with `_Release` pydantic model + `GET /api/user/collection` route body (token routing, magic-token error injection, pagination math).
- `pyproject.toml` — added `cryptography>=48`, `stamina>=26` runtime deps + `pytest-httpx>=0.36` dev dep.
- `uv.lock` — regenerated for the three new packages.

## Decisions Made

- **Two nested stamina.retry_context loops** in `_get_page` (network outer, HTTP inner). Rationale: stamina's single `attempts` parameter can't express different budgets per error class; nesting two loops (outer attempts=2, inner attempts=4) is the cleanest way to honor "429 exhausts at 4 calls AND network exhausts at 2 calls" under one `_get_page` implementation.
- **Lazy os.environ read for GRUVAX_SECRET_KEY** in `_fernet()`. Rationale: sibling Plan 01-01 (Settings extension) is in flight on a separate worktree; reading via `os.environ` rather than `settings.GRUVAX_SECRET_KEY` decouples this plan from Settings's attribute schema, AND allows the Alembic migration to import `pat_crypto` for the seed-row placeholder without bootstrapping Settings.
- **`decrypt_pat` re-raises InvalidToken**. Rationale: silent return would orphan the row in a confusing "PAT present but unusable" state; the caller (sync_profile) translates InvalidToken to `last_sync_error='pat_rejected'` which is operator-actionable.
- **PATRejected fixed-string message**: `"PAT rejected by discogsography (401/403)"`. Rationale: NEVER include the Authorization header or response body — httpx error reprs can quote bodies that could in turn quote headers. Test 11 LEAK_DETECTOR sentinel asserts no PAT plaintext leaks.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Worktree missing .env file**
- **Found during:** Task 1 (test collection)
- **Issue:** pytest failed at conftest import because `gruvax.db.pool` instantiates `Settings()` at module load, requiring `DATABASE_URL` + `SESSION_SECRET`. Worktrees spawned by Claude Code don't inherit the parent's `.env` file.
- **Fix:** Copied `/Users/Robert/Code/public/GRUVAX/.env` into the worktree (file is gitignored, so it does NOT enter the commit history).
- **Files modified:** `.env` (gitignored)
- **Verification:** All 34 plan tests + 22 pre-existing logging tests pass.
- **Committed in:** N/A (gitignored).

**2. [Rule 3 - Blocking] Plan PATTERNS §1 retry decorator pattern doesn't separate budgets**
- **Found during:** Task 3 (implementing `_get_page`)
- **Issue:** Plan RESEARCH §Pattern 1 shows `@stamina.retry(on=_should_retry, attempts=3)` — a single decorator with one `attempts` parameter. But the per-test semantics require 3 retries for 429/5xx (4 total calls) AND 1 retry for network (2 total calls).
- **Fix:** Replaced the single decorator with two nested `stamina.retry_context` loops — outer for network errors (`attempts=2`), inner for HTTP errors (`attempts=4`). Network errors never reach the HTTP loop; HTTP errors never trigger network retries. Test 4 (429 → 4 calls) and Test 7 (network → 2 calls) both pass under one `_get_page`.
- **Files modified:** `src/gruvax/discogsography/client.py`
- **Verification:** All 11 retry tests pass.
- **Committed in:** `04a3343`

**3. [Rule 3 - Blocking] Stamina exhaustion propagates exception out of the async for loop**
- **Found during:** Task 3 (initial Test 4 run)
- **Issue:** First implementation had post-loop `if last_http_exc: raise RateLimitExhausted(...)` — but stamina re-raises the last exception out of the `async for` loop, so the post-loop translation code was unreachable.
- **Fix:** Wrapped the entire `async for` loop in `try/except HTTPStatusError` and translated to typed errors there. Same pattern applied to the outer (network) loop.
- **Files modified:** `src/gruvax/discogsography/client.py`
- **Verification:** Tests 4 and 6 now correctly raise the typed errors.
- **Committed in:** `04a3343`

---

**Total deviations:** 3 auto-fixed (1 worktree-env, 2 implementation-pattern adjustments)
**Impact on plan:** None on scope. The two implementation-pattern adjustments are mechanical consequences of stamina's exception-propagation model that PATTERNS.md couldn't pre-empt without running the tests. The worktree .env copy is the universal Claude-Code-worktree pattern (already documented in MEMORY).

## Issues Encountered

- **Python 3.14 PEP 758 syntax**: ruff format converted `except (TypeError, ValueError):` to the PEP-758 unparenthesized form `except TypeError, ValueError:` on a line without `as e:`. Initially looked like broken syntax, but Python 3.14 accepts it. Left as ruff's preferred form for `target-version = "py314"`.
- **`tests/conftest.py:46` deprecation warning** about `asyncio.DefaultEventLoopPolicy` is pre-existing, unrelated to this plan.

## Threat Flags

None. All security-relevant surfaces introduced (PAT egress, log redaction, Fernet at-rest) were already in the plan's `<threat_model>` register.

## Self-Check: PASSED

- All 14 expected files present (verified via `[ -f "$f" ]` per path).
- All 3 task commits present in `git log --oneline --all` (5226b1e, 4560213, 04a3343).
- `uv run pytest tests/unit/discogsography/ --no-header --benchmark-skip` → **34 passed, 1 warning in 7.06s** (the warning is pre-existing `asyncio.DefaultEventLoopPolicy` deprecation in conftest.py:46, unrelated to this plan).
- `uv run ruff check src/gruvax/discogsography/ src/gruvax/sync/ src/gruvax/_internal/fake_discogsography.py src/gruvax/logging_config.py tests/unit/discogsography/` → All checks passed.
- `uv run ruff format --check ...` → 14 files already formatted.

## Known Stubs

None. Every file ships with the full functionality the plan requires. The Wave-0 SHELL at `src/gruvax/_internal/fake_discogsography.py` has been fully fleshed out per Plan 02 Task 2.

## User Setup Required

None — no external service configuration. Plan 04 will introduce the `gruvax-set-pat` CLI for PAT bootstrap, but Plan 02's primitives are import-time-safe even without `GRUVAX_SECRET_KEY` set.

## Next Phase Readiness

Plan 03 (sync_profile staging-swap) can now import:
- `gruvax.discogsography.client.DiscogsographyClient` for paged collection fetch.
- `gruvax.discogsography.errors.{PATRejected, RateLimitExhausted, ServerError, NetworkError, SyncInProgress}` for typed error mapping to `last_sync_error` tags.
- `gruvax.sync.pat_crypto.{encrypt_pat, decrypt_pat}` for the PAT decrypt at sync start.

Plan 04 (`gruvax-set-pat` / `gruvax-sync` CLIs) can now import the same surface plus call `client.fetch_user_id()` for the inline test-sync (D-08).

Plan 05 (Compose `fake-discogsography` sibling service) can `from gruvax._internal.fake_discogsography import create_fake_app` directly — no module duplication.

**Concurrency note:** This plan is on a separate worktree from sibling Plan 01-01 (settings.py + migration + db/pool.py). Files do NOT overlap. Sibling's Settings extension (`GRUVAX_SECRET_KEY` field) is forward-compatible with this plan's `os.environ` read in `pat_crypto._fernet()`.

---
*Phase: 01-walking-skeleton-api-client-single-profile-sync*
*Completed: 2026-05-27*

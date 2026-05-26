---
phase: 9
slug: tooling-and-docs-hardening
status: secured
threats_open: 0
threats_total: 21
threats_closed: 21
asvs_level: 1
block_on: high
created: 2026-05-25
---

# GRUVAX Security Audit — Phase 9 (Tooling & Docs Hardening)

**Audit date:** 2026-05-25
**Phase:** 09 — tooling-and-docs-hardening
**ASVS Level:** 1
**block_on:** high
**Auditor:** gsd-security-auditor (Claude Sonnet 4.6)
**Verdict:** SECURED — 21/21 threats closed

---

## Threat Verification

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-9-IL | Information Disclosure | mitigate | CLOSED | `logging_config.py:172` — `getLogger("gruvax")` only, never root; `tests/integration/test_diagnostics.py:290` — `test_recent_logs_ring_scoping` asserts psycopg/uvicorn/sqlalchemy/aiomqtt prefixes absent |
| T-9-TAMPER | Tampering | mitigate | CLOSED | `logging_config.py:80-98` — `emit()` reads `record.msg`, `record.created`, `record.levelname`, `record.name` only; zero mutation of any record field confirmed by grep (no assignment to `record.*`) |
| T-9-SHAPE | Repudiation | mitigate | CLOSED | `tests/integration/test_diagnostics.py:269-285` — `test_recent_logs_shape` asserts `set(entry.keys()) == {"ts", "level", "logger", "msg"}` and type checks float/str on every entry |
| T-9-PERM | Elevation of Privilege | mitigate | CLOSED | `build.yml:28` — workflow-level `permissions: contents: read`; `build.yml:53-54` — `packages: write` scoped to build job only; `build.yml:45-46` — `security-events: write` scoped to run-security job only |
| T-9-SC | Tampering | mitigate | CLOSED | All 27 `uses:` lines across six workflows pinned to 40-char SHAs; no `@vN` floating tags found (`grep -rE 'uses:.*@v[0-9]'` returns nothing); `security.yml:59` — semgrep container `image: semgrep/semgrep@sha256:7cad2bc2d1e44f87f0bf4be6d1fa23aa90fb72015bebc89fb91385d813987a03` (CR-01 fix applied in plan 08) |
| T-9-TOKEN | Information Disclosure | mitigate | CLOSED | `build.yml:69` — `secrets.GITHUB_TOKEN`; `build.yml:64` — login-action guarded by `github.event_name != 'pull_request'`; `build.yml:87` — push similarly gated; no plaintext PATs in any workflow file |
| T-9-CSV | Information Disclosure | mitigate | CLOSED | `test.yml:77` — seeds only `fixtures/synth_collection.sql`; comment on lines 4-5 and 75 explicitly states "NEVER seeds the real collection CSV or background/"; no other seed commands in test.yml |
| T-9-SECRETSCAN | Information Disclosure | mitigate | CLOSED | `security.yml:107-111` — TruffleHog step (`trufflesecurity/trufflehog@37b77001...`) runs over full repo; all workflow secrets referenced via `secrets.*` or `github.token` only; no hardcoded credentials found |
| T-9-DEPBOT | Tampering | accept | CLOSED | Accepted: dependabot opens PRs only; no auto-merge configured in `.github/dependabot.yml`; human review required before merge. Home-LAN, no-public-exposure project — residual risk appropriate. |
| T-9-HOOKPIN | Tampering | mitigate | CLOSED | `.pre-commit-config.yaml` — all 10 `rev:` lines are 40-char SHAs (grep confirms; no floating `rev: v?[0-9]+\.` found); each annotated with `# frozen: vX` comment |
| T-9-UPDLOCK | Tampering | accept | CLOSED | Accepted: `scripts/update-project.sh:76` — script ends with "Review git diff for surprising version jumps before committing"; operator review step explicitly present. |
| T-9-BANDIT | Information Disclosure | mitigate | CLOSED | `.pre-commit-config.yaml:48-49` — bandit hook present with `args: [-x, "tests", -s, "B608"]`; also present in `security.yml:48` — `uv run bandit -x tests -s B608 -r src/` |
| T-9-FIXREGRESS | Tampering | mitigate | CLOSED | `ruff check src/ tests/` exits 0 (verified); `grep -rn 'pytest.raises(Exception)' tests/` returns nothing; `tests/unit/test_logging_config.py` and `tests/integration/test_diagnostics.py` pass per plan 07 self-check (460 passed) |
| T-9-GATEHOLE | Repudiation | mitigate | CLOSED | `ruff check src/ tests/` exits 0 (verified live); `grep -rc 'continue-on-error' .github/workflows/` — only two comment-line matches in test.yml (lines 8, 91), zero YAML-directive matches; `build.yml` aggregate-results job enforces hard fail |
| T-9-B608 | Information Disclosure | accept | CLOSED | Accepted: SIM105 fix in Plan 04 narrowed contextlib.suppress to exact exception being swallowed (ruff `--select SIM105` exits 0 on all src/ files); bandit B608 gate remains in both pre-commit and security.yml. |
| T-9-OVERRIDE | Tampering | mitigate | CLOSED | `git check-ignore compose.override.yaml` returns exit 0 (confirmed); `.gitignore` has entry `compose.override.yaml`; `compose.override.yaml.example` committed with explicit "IMPORTANT: must NEVER be deployed to production host" warning; `docs/runbook-fresh-host.md` documents the Pitfall 3 constraint |
| T-9-IMGSPOOF | Spoofing | accept | CLOSED | Accepted: public GHCR package for open-source home-LAN project; image published only by SHA-pinned build job with least-privilege `packages: write` scoped to build job; no public exposure per project constraints. |
| T-9-LUXLEAK | Information Disclosure | mitigate | CLOSED | `grep -c 'lux' compose.yaml` returns 0 (verified); `grep -c 'lux' docs/runbook-fresh-host.md` returns 0 (verified); all four lux comments in compose.yaml genericized to "deployment host" |
| T-9-DOCLEAK | Information Disclosure | mitigate | CLOSED | `grep -c 'lux' README.md` returns 0; `grep -c 'lux' CLAUDE.md` returns 0; `grep -c 'lux' docs/ARCHITECTURE.md` returns 0 (all verified live) |
| T-9-DOCDRIFT | Repudiation | mitigate | CLOSED | `docs/ARCHITECTURE.md` API Surface section (lines 59-101) lists health, search, locate, units, illuminate, events, version public endpoints and full admin surface; verified against `src/gruvax/app.py` router registrations (health, search, locate, units, illuminate, version, admin, events — all match); `v_collection` referenced (line 10+ verified) |
| T-9-DOCSECRET | Information Disclosure | accept | CLOSED | Accepted: docs describe public architecture only; no credentials, PINs, or session secrets appear in README.md, CLAUDE.md, or docs/ARCHITECTURE.md; secrets remain in env/.env/GitHub Secrets per project pattern. |

---

## Unregistered Flags

None. All threat flags from the phase SUMMARY files (Plans 01–08) map to entries in the threat register above. Plan 07 SUMMARY introduced no new attack surface (pre-commit hook fixes only). Plan 08 SUMMARY applied CR-01 (semgrep pin, already registered under T-9-SC) and WR-02 (logging idempotency — defensive hardening, not a new threat).

---

## Accepted Risks Log

| Threat ID | Rationale | Residual Risk |
|-----------|-----------|---------------|
| T-9-DEPBOT | Dependabot opens PRs only; human merges. No auto-merge. Home-LAN project with no public exposure. | Low |
| T-9-UPDLOCK | Operator reviews `git diff` before committing lockfile changes; script ends with explicit review reminder. | Low |
| T-9-B608 | contextlib.suppress narrowed to exact exception; bandit B608 remains gated in both pre-commit and security.yml. | Low |
| T-9-IMGSPOOF | GHCR public package for open-source home-LAN app; image publish gated by SHA-pinned, least-privilege build job. | Low |
| T-9-DOCSECRET | Docs contain only public architecture descriptions; no secrets committed. | None |

---

## Notes

**CR-01 (semgrep image pin):** The code review (09-REVIEW.md) identified the unpinned semgrep container as critical. Plan 08 applied the fix: `semgrep/semgrep@sha256:7cad2bc2d1e44f87f0bf4be6d1fa23aa90fb72015bebc89fb91385d813987a03` (v1.163.0). T-9-SC is verified CLOSED including this fix.

**WR-04 (stalenessStatus null badge):** Deferred by Plan 08 as pre-existing product behavior, out of scope for this no-behavior-change phase. Not a threat registered in the Phase 9 threat model; tracked for the next admin UI iteration.

**Deferred item (not a BLOCKER):** `scripts/update-project.sh` WR-01 (--major dead branch) was fixed in Plan 08. T-9-UPDLOCK remains an accepted risk independent of this fix.

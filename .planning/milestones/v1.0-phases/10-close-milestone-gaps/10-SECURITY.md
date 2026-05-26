---
phase: 10
slug: close-milestone-gaps
status: secured
threats_open: 0
threats_total: 6
threats_closed: 6
asvs_level: 1
block_on: high
created: 2026-05-26
---

# GRUVAX Security Audit — Phase 10 (Close Milestone Gaps)

**Audit date:** 2026-05-26
**Phase:** 10 — close-milestone-gaps
**ASVS Level:** 1
**block_on:** high
**Auditor:** gsd-security-auditor (Claude Sonnet 4.6)
**Verdict:** SECURED — 6/6 threats closed
**Register origin:** `register_authored_at_plan_time: true` (all three PLAN.md files carry parseable `<threat_model>` blocks; the auditor verified mitigations against implementation rather than retroactively building a STRIDE register)

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| admin (mobile) → segment-edit API | `PUT /api/admin/cubes/{u}/{r}/{c}/cut`, `POST /overrides`, `POST /insert-cut`; gated by `require_admin` (CSRF + admin session) | Cut points, override fractions, change-set ids — non-PII boundary configuration |
| admin (mobile) → history revert API | `POST /api/admin/history/{id}/revert`; gated by `require_admin` | Change-set id (UUID), conflict-detection timestamps |
| API → kiosk (SSE) | Server-produced `boundary_changed` frames (rename in 10-01) and new revert publish (10-02) | Cube coordinates `{unit, row, col}` and `change_set_id` — no auth secrets, no PII |
| API → `gruvax.segment_overrides` (private schema) | Post-transaction SELECT during revert (10-02) over the existing connection pool | `(unit, row, col, label, fraction)` — boundary configuration, not PII |

Out of band for Phase 10: planning markdown edits (10-03) cross no runtime boundary.

---

## Threat Verification

| Threat ID | Category | Component | Disposition | Status | Evidence |
|-----------|----------|-----------|-------------|--------|----------|
| T-10-01 | Tampering | `segments.py` `boundary_changed` publishes (rename only — 10-01) | accept | CLOSED | `require_admin` present at all four segment endpoint signatures (`segments.py` lines 131, 181, 328, 457). All three `bus.publish("boundary_changed", ...)` payloads use `"cube_ids"` (lines 298, 440, 685) with `"unit"` inner key (`affected_cubes.append` at line 661). Zero occurrences of the old `"cubes"` key or a top-level `"type"` key in any publish block. The dict-key rename does not alter the auth/validation surface. |
| T-10-02 | Denial of Service | KioskView SSE handlers (10-01 IN-02 hardening) | mitigate | CLOSED | `boundary_changed` handler (`KioskView.tsx` lines 241-264) and `admin_editing` handler (lines 270-283) are each wrapped in `try { ... } catch (err) { console.error('[SSE] <event> parse error — degrading gracefully', err) }`. `grep -c "console.error" KioskView.tsx` returns exactly 2 — one per handler; neither catch block is silent. A malformed frame cannot terminate the SSE handler / silently degrade the live-update loop. |
| T-10-03 | Tampering | `revert_change_set` new dependency injections (10-02) | accept | CLOSED | `revert_change_set` retains `_admin: dict[str, Any] = Depends(require_admin)` (`history.py` line 86). Three new deps injected via `Depends()` — `get_segment_cache` (line 83), `get_collection_snapshot` (line 84), `get_event_bus` (line 85) — all read from `request.app.state` (in-memory only). No new external input surface; auth gate unchanged. |
| T-10-04 | Information Disclosure | overrides SELECT from `gruvax.segment_overrides` (10-02) | accept | CLOSED | `SELECT unit_id, row, col, label, fraction FROM gruvax.segment_overrides` (`history.py` line 222) reads the app's own private schema table over the existing pool. Columns are numeric coordinates + fraction float + label string — boundary configuration, not PII. Same data is already exposed via admin endpoints. Read happens inside a handler gated by `require_admin`; no new disclosure surface. |
| T-10-05 | Tampering | planning-markdown edits — `REQUIREMENTS.md`, `ROADMAP.md` (10-03) | accept | CLOSED | `.planning/REQUIREMENTS.md` and `.planning/ROADMAP.md` are non-deployed planning artifacts. Phase 10 commits `5cb0589`, `501a63f` touch only markdown — no executable code, no secrets, no runtime surface. Internal-consistency check (84 = 75 satisfied + 9 deferred) is the only correctness gate, and the verifier confirmed it (10-VERIFICATION.md status: passed). |
| T-10-SC | Tampering | Supply chain (npm / pip / cargo installs) | accept | CLOSED | All seven Phase 10 code/docs commits (`db72a3e`, `fe30464`, `b3f557c`, `cc156cf`, `894834c`, `5cb0589`, `501a63f`) audited against `pyproject.toml` and `frontend/package.json` — zero package-manifest changes in any commit. No new pip / npm / cargo dependencies introduced; no slopcheck checkpoint required. |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-10-01 | T-10-01 | Three publish-payload key renames in `segments.py` change wire shape only; the endpoints already enforce `require_admin` (CSRF + admin session). The rename is a *correction* to the canonical contract (`cube_ids` / `unit`) used by every other producer (`cubes.py`, `import_.py`) and the consumer (`KioskView.tsx`). No new attack surface. | Auditor (Sonnet 4.6) | 2026-05-26 |
| AR-10-03 | T-10-03 | `revert_change_set`'s new `Depends()` deps are *in-memory app-state accessors* (`get_segment_cache`, `get_collection_snapshot`, `get_event_bus`); none take untrusted input. The endpoint retains `require_admin`. The DI list grew; the auth boundary did not. | Auditor (Sonnet 4.6) | 2026-05-26 |
| AR-10-04 | T-10-04 | The new `SELECT ... FROM gruvax.segment_overrides` reads the app's own private schema over the existing pool, inside a handler gated by `require_admin`. The columns (`unit, row, col, label, fraction`) are non-PII boundary configuration already reachable through other admin endpoints. No information-disclosure expansion. | Auditor (Sonnet 4.6) | 2026-05-26 |
| AR-10-05 | T-10-05 | `REQUIREMENTS.md` and `ROADMAP.md` are non-deployed planning artifacts. Editing them ships nothing to production: no runtime surface, no executable code, no secret material. The traceability reconcile (SEG-01..08 → Complete, 81→84 header, 73→84 ROADMAP intro) is information accuracy, not a code or auth change. | Auditor (Sonnet 4.6) | 2026-05-26 |
| AR-10-SC | T-10-SC | Phase 10 introduced **zero** new package dependencies — verified by inspecting all seven Phase 10 code/docs commits against `pyproject.toml` and `frontend/package.json`. The supply-chain attack surface is unchanged; no slopcheck required. | Auditor (Sonnet 4.6) | 2026-05-26 |

*Accepted risks are documented and do not resurface in future audit runs.*

---

## Unregistered Threat Flags

None. The three SUMMARY.md `## Threat Flags` sections (10-01, 10-02, 10-03) all explicitly state "None." No executor-reported attack surface was introduced outside the plan-time register.

---

## Pre-existing Issues (Out of Scope)

Two `critical` findings from `10-REVIEW.md` predate Phase 10 (confirmed via `git diff` of every Phase 10 commit's touch on the file in question) and are intentionally **out of scope** of this audit. They are flagged here so they are not lost:

| Ref | Origin | File | Concern |
|-----|--------|------|---------|
| CR-01 | Phase 5 (segment-aware precision) | `src/gruvax/api/admin/segments.py::put_bin_cut` (lines 282-293) | Collects overrides from the stale single-bin `segment_cache` and passes a partial dict to `segment_cache.derive()` (a full rebuild). On rebuild, every other bin's admin-set width override is silently dropped. The other three write paths (`set_bin_overrides`, `insert_cut`, the new `revert_change_set`) correctly re-read all overrides from `gruvax.segment_overrides`. |
| CR-02 | Phase 3 (admin loop / history revert) | `src/gruvax/api/admin/history.py` (`fetch_change_set_rows` ~lines 135-138 + `has_newer_changes` conflict guard) | `changed_at` is `.isoformat()`-stringified before being passed back into a `changed_at > %s` (`timestamptz > text`) comparison, relying on PostgreSQL implicit cast. Type-unsafe; a session with a different timezone configuration could quietly skip the T-03-21 silent-clobber guard. |

These belong to a focused follow-up phase (recommend: a Phase 5 / Phase 3 hardening cycle). Phase 10 deliberately does not expand scope to address pre-existing code.

---

## Audit Trail

| Event | Date | Detail |
|-------|------|--------|
| Threat register authored (plan-time) | 2026-05-25 | All 3 PLAN.md files include `<threat_model>` blocks with trust boundaries + STRIDE register; planner verified consistent disposition rationale (no new high/medium threats introduced by INT-A / INT-B / traceability work). |
| Plan checker review | 2026-05-25 | Independent 12-dimension review (10-VERIFICATION.md ancestor); threat_model blocks present on each plan; quality gate satisfied. |
| Execution | 2026-05-25 | 3/3 plans completed; full pytest suite 466 passed (post-merge), mypy --strict clean, frontend build clean. |
| Code review | 2026-05-25 | `/gsd-code-review 10` standard depth; no new criticals introduced by Phase 10. Two pre-existing criticals flagged for follow-up (CR-01, CR-02 — see "Pre-existing Issues" above). |
| Goal verification | 2026-05-25 | 10/10 automated must-haves verified; 2 human-only items deferred. |
| Human UAT | 2026-05-25 | 10-HUMAN-UAT.md complete — highlight-follows-record after a real segment edit verified live on the kiosk (Test 2 PASS); defensive try/catch (Test 1) skipped as code-verified. 10-VERIFICATION.md reconciled `human_needed → passed`. |
| Security audit (this run) | 2026-05-26 | gsd-security-auditor verified all 6 register entries against the implementation; no implementation gaps; no unregistered attack surface; supply chain unchanged. |

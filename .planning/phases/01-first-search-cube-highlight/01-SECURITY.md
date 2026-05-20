---
phase: 01
slug: first-search-cube-highlight
status: secured
threats_open: 0
asvs_level: 1
created: 2026-05-20
---

# SECURITY.md — Phase 1: First Search → Cube Highlight

**Audit Date:** 2026-05-20
**ASVS Level:** 1 · **block_on:** high
**Auditor:** gsd-security-auditor (automated) + orchestrator remediation
**Result:** 15/15 threats resolved (12 mitigated, 3 accepted) — `threats_open: 0`

---

## Threat Verification Summary

| Metric | Count |
|--------|-------|
| Threats in register | 15 |
| Mitigated (verified in code) | 12 |
| Accepted (documented) | 3 |
| Open (BLOCKER) | 0 |

The register was authored at plan time (every PLAN.md carries a `<threat_model>`),
so the auditor verified each mitigation against the implementation rather than
scanning for new threats. One BLOCKER (T-01-13) was found during the audit and
**fixed during this run** (commit recorded below).

---

## Threat Register — Dispositions & Evidence

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-01-01 | Elevation of Privilege | mitigate | CLOSED | `migrations/versions/0002_v_collection_view.py` GRANT SELECT only; `justfile` `provision-db` echoes SELECT-only grants ("No INSERT/UPDATE/DELETE"); view is read-only |
| T-01-02 | Information Disclosure | mitigate | CLOSED | `.gitignore` contains `background/` + `*.csv`; only synthetic PII-free fixtures committed |
| T-01-03 | Tampering | accept | CLOSED | Single-operator home project; migrations version-controlled + `just migrate-roundtrip` gate |
| T-01-04 | Tampering | mitigate | CLOSED | `estimator/normalize.py` `parse_key`/`catalog_in_range`; `algorithm.py:82` only comparison path; no raw string compare; Hypothesis total-order properties |
| T-01-05 | Denial of Service | mitigate | CLOSED | `normalize.py` `_DIGIT_CAP=12` applied before `int()`; Hypothesis fuzz bounded |
| T-01-06 | Information Disclosure | accept | CLOSED | `LocateResult` exposes cube position only; no-boundary → HTTP 200 `confidence=0.0`/`primary_cube=None`, not an error leak |
| T-01-07 | Tampering (SQLi) | mitigate | CLOSED | `db/queries.py` all SQL uses `%s` placeholders; params passed as tuple; no f-string SQL; SQLi integration test |
| T-01-08 | Denial of Service | mitigate | CLOSED | `api/search.py` `limit: int = Query(ge=1, le=50)` → 422 |
| T-01-09 | Tampering | mitigate | CLOSED | `api/locate.py` `release_id: int` typed → 422 |
| T-01-10 | Denial of Service | mitigate | CLOSED | `api/search.py` `q: str = Query(min_length=1, max_length=200)` → 422 |
| T-01-11 | Denial of Service | mitigate | CLOSED | `mqtt/client.py` `connect_mqtt` wrapped in `try/except`; failure → degraded, never blocks request path |
| T-01-12 | Spoofing/Tampering | mitigate (no-ports) + accept (auth → P5) | CLOSED | `compose.yaml` mosquitto has **no `ports:`** (internal-only). Broker auth (`password_file`) deferred to Phase 5 — see Accepted Risks |
| T-01-13 | Information Disclosure | mitigate | **CLOSED (fixed this run)** | `app.py` `SpaStaticFiles.get_response` sets `Cache-Control: no-store` on `text/html`; Vite content-hashed assets stay cacheable. Verified live: `GET /` → `cache-control: no-store`; `/assets/*.js` → no no-store. Regression test `tests/integration/test_health.py::test_index_html_no_store` |
| T-01-14 | Tampering | mitigate | CLOSED | `app.py` all `/api/*` routers `include_router` before `app.mount(StaticFiles)` (Pitfall 3) |
| T-01-15 | Information Disclosure | accept | CLOSED | Grep gate: no 6-digit hex in `frontend/src`; design-token contract is the single source |
| T-01-SC | Tampering (supply chain) | mitigate | CLOSED | `uv.lock` + `frontend/package-lock.json` committed; all packages registry-verified (RESEARCH audit), none flagged [SUS]/[SLOP] |

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Phase to Revisit |
|---------|------------|-----------|------------------|
| AR-01 | T-01-03 | Alembic migrations tampering accepted: single-operator home project, version-controlled + round-trip-tested | — |
| AR-02 | T-01-06 | LocateResult exposes cube position only; no PII surface on the public endpoint | — |
| AR-03 | T-01-12 (auth) | Mosquitto `allow_anonymous true`; broker is internal-only (no host ports) and has no publish path in v1. Full broker auth (`password_file`) is a Phase 5 (LED/MQTT) deliverable. | **Phase 5** |

*Accepted risks do not resurface in future audit runs.*

---

## Remediation This Run

- **T-01-13 (BLOCKER → CLOSED):** added `SpaStaticFiles` subclass in `src/gruvax/app.py` that sets `Cache-Control: no-store` on `text/html` responses (the SUMMARY's earlier "no-store is a StaticFiles default" claim was incorrect — `html=True` is SPA fallback only). Verified live against the running container and covered by a regression test. Rebuilt + redeployed.

---

## Unregistered Threat Flags

None. No attack surface appeared during implementation beyond the registered threats.

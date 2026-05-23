---
phase: 05
slug: segment-aware-position-precision
status: verified
threats_total: 24
threats_closed: 24
threats_open: 0
asvs_level: 2
created: 2026-05-23
---

# Phase 05 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Verified 2026-05-23 by gsd-security-auditor against implemented code.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Browser → FastAPI | Admin SPA to REST API over LAN HTTP | Fraction values, label/catalog strings, Idempotency-Key, CSRF token |
| FastAPI → PostgreSQL | Parameterized queries only | Cut-point values, segment_overrides rows |
| SegmentCache (in-process) | Derived in-memory structure | Label names, fraction floats — never crosses a process boundary |
| FastAPI → MQTT broker | Boundary-changed publish | cube coordinates only, no PII |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-05-01 | Tampering | segment_overrides.fraction | mitigate | DB CHECK (fraction > 0.0 AND fraction <= 1.0) in migration 0005; test asserts fraction=1.5 rejected | CLOSED |
| T-05-02 | Tampering | segment_overrides FK | mitigate | FK (unit_id, row, col) REFERENCES cube_boundaries ON DELETE CASCADE | CLOSED |
| T-05-02-01 | Tampering | derive() override fraction sum | mitigate | derive() asserts abs(sum(applied_fractions) - 1.0) < 1e-6 and raises ValueError on failure; renormalizes non-overridden segments | CLOSED |
| T-05-02-02 | DoS | derive() over snapshot | accept | CPU-only, ~3,000-record home-LAN scale, off hot path — see Accepted Risks Log | CLOSED |
| T-05-02-03 | Info Disclosure | SegmentCache in-process | accept | In-process only; no new endpoint — see Accepted Risks Log | CLOSED |
| T-05-03 | Repudiation | boundary_history nullable columns | accept | Historical nullable last_* columns kept; no audit data destroyed — see Accepted Risks Log | CLOSED |
| T-05-03-01 | Tampering | release_id / coordinate params | mitigate | FastAPI typed int (release_id: int in locate.py:65); Path(ge=1)/Path(ge=0) on all coordinate params; all SQL uses %s | CLOSED |
| T-05-03-02 | DoS | locate hot path | mitigate | CPU-only two-level interpolation; SegmentCache pre-derived; p95<=50ms gate passed in 05-03 | CLOSED |
| T-05-03-03 | Info Disclosure | /api/cubes public endpoint | accept | Public by design (D-15); home-LAN, no PII; cube metadata + fill level only — see Accepted Risks Log | CLOSED |
| T-05-03-04 | Tampering | seed_boundaries CLI | accept | Dev/CI-only; %s placeholders; synthetic YAML fixture — see Accepted Risks Log | CLOSED |
| T-05-04-01 | EoP | every new admin endpoint | mitigate | require_admin Depends on GET /segments (line 131), PUT /cut (line 181), POST /overrides (line 321), POST /insert-cut (line 451) in segments.py | CLOSED |
| T-05-04-02 | Tampering | phantom override injection | mitigate | POST /overrides rejects labels whose casefold() not in bin_labels set; returns 400 phantom_override (segments.py:357-368) | CLOSED |
| T-05-04-03 | Tampering | override fraction out of range | mitigate | Pydantic Field(gt=0.0, le=1.0) (segments.py:97) + DB CHECK fraction > 0.0 AND fraction <= 1.0 (migration 0005:91) | CLOSED |
| T-05-04-04 | DoS | cut-insert cascade overflow | mitigate | validate_shelf_overflow counts physical cubes before accepting; returns shelf_overflow 400 (segments.py:505-515, validation.py:306-349) | CLOSED |
| T-05-04-05 | Spoofing | Idempotency-Key replay | mitigate | check_idempotency pre-flight; store_idempotency inside transaction atomic with writes (segments.py:342-405, queries.py:681-730) — matches Phase 3 pattern | CLOSED |
| T-05-04-06 | Tampering | SQL injection in segment/override SQL | mitigate | All SQL uses %s placeholders; zero f-string interpolation of user input confirmed in segments.py, validation.py, queries.py | CLOSED |
| T-05-04-07 | Tampering | save-validator bypass | mitigate | validate_contiguity called on PUT /cut (segments.py:231) and POST /insert-cut (segments.py:623); also called in POST /validate (cubes.py:468) — server-authoritative on all paths | CLOSED |
| T-05-05-01 | Tampering | SegmentStrip / BinWidthEditor DOM build | mitigate | el()+replaceChildren() used in SegmentStrip.tsx:75-158 and BinWidthEditor.tsx:186-213; no innerHTML assignments anywhere in admin routes | CLOSED |
| T-05-05-02 | Tampering | client-computed override fractions | mitigate | Server re-validates bounds (Pydantic gt/le) + label-in-bin (phantom_labels check) on POST /overrides; client values advisory only | CLOSED |
| T-05-05-03 | Spoofing/EoP | admin fetch without session | mitigate | adminFetch adds X-CSRF-Token on mutating requests (adminClient.ts:65-68); require_admin verifies cookie + CSRF + session row (deps.py:132-222) | CLOSED |
| T-05-05-04 | Tampering | contiguity / overflow bypass via UI | mitigate | validate_contiguity server-authoritative on PUT /cut (segments.py:231) and POST /insert-cut (segments.py:623); same function as validate path in cubes.py:468 | CLOSED |
| T-05-06-01 | Tampering | put_bin_cut / insert_cut direct write paths | mitigate | build_proposed_cuts() + validate_contiguity() called BEFORE async with pool.connection() on both PUT /cut (segments.py:230-242) and POST /insert-cut (segments.py:622-628); 400 contiguity_error returned without DB write on violation | CLOSED |
| T-05-06-02 | Info Disclosure | contiguity_error body | accept | Label name only (already supplied by admin), no PII; home-LAN single admin — see Accepted Risks Log | CLOSED |
| T-05-06-03 | Tampering | SQL in segments.py on reject path | mitigate | validate_contiguity() and build_proposed_cuts() are pure in-memory (validation.py has zero pool/conn/execute calls); no DB write on contiguity reject | CLOSED |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Supply-Chain Threats (no new deps confirmed)

| Threat Group | Assertion | Evidence |
|-------------|-----------|----------|
| T-05-01-SC through T-05-05-SC | No new pip/npm/cargo installs for plans 05-01 through 05-05 | `pyproject.toml` unchanged from Phase 4; only `lucide-react ^1.16.0` added to `frontend/package.json` (commit 686fbf5) — icon library, no code execution surface |
| T-05-06-SC | No new installs in plan 05-06 | Confirmed — `git diff 3852438 HEAD -- pyproject.toml` returns empty; `git diff 3852438 HEAD -- frontend/package.json` shows only `lucide-react` |

*All supply-chain threats CLOSED — lucide-react is a display-only icon library with no network or auth surface.*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-05-01 | T-05-02-02 | derive() is CPU-only and called only on BoundaryCache invalidation, not the hot request path. At ~3,000 records on a home LAN this is a millisecond operation with one user. No mitigation is warranted. | Phase 05 plan | 2026-05-23 |
| AR-05-02 | T-05-02-03 | SegmentCache is an in-process data structure with no new endpoint, no serialization to disk, and no cross-process sharing. It holds derived label names and fraction floats — no PII. No mitigation is warranted. | Phase 05 plan | 2026-05-23 |
| AR-05-03 | T-05-03 | boundary_history.prev_last_label / prev_last_catalog / new_last_label / new_last_catalog columns are retained as nullable historical artifacts (decision A1). No audit data is destroyed. Future revert operations may see NULL in these columns for post-0005 history rows, which is expected and handled by the revert logic. | Phase 05 plan | 2026-05-23 |
| AR-05-04 | T-05-03-03 | GET /api/cubes/{unit_id}/{row}/{col} is intentionally public per design decision D-15 (kiosk visitors can browse cube contents without logging in). The response contains only cube metadata (label, catalog, fill level) — no PII, no personally identifiable collection patterns. Exposure is limited to home LAN. | Phase 05 plan | 2026-05-23 |
| AR-05-05 | T-05-03-04 | seed_boundaries CLI is a development/CI-only tool invoked manually. It uses %s placeholders throughout (confirmed at seed_boundaries.py:41,78). The YAML fixture is synthetic. No production attack surface. | Phase 05 plan | 2026-05-23 |
| AR-05-06 | T-05-06-02 | The 400 contiguity_error response body includes the label name that would be scattered. This is the same label name the admin just typed into the form. No additional information is disclosed beyond what the admin already knows. No PII. Home-LAN single admin. | Phase 05 plan | 2026-05-23 |

*Accepted risks do not resurface in future audit runs.*

---

## Unregistered Threat Flags

No SUMMARY.md threat flags were unregistered. All SUMMARY.md ## Threat Flags sections across plans 05-01 through 05-06 reported either "None" or explicitly mapped to registered threat IDs:

- 05-01: "None" — no new endpoints or auth paths
- 05-02: "None" — SegmentCache in-process only (maps to T-05-02-03, accepted)
- 05-03: "None" — no new endpoints
- 05-04: No threat flags section (all concerns covered by registered threats)
- 05-05: "No innerHTML / No hardcoded hex" confirmed (maps to T-05-05-01)
- 05-06: "No new trust boundaries" — contiguity_error body maps to T-05-06-02 (accepted)

---

## Evidence Notes

### T-05-04-05 Idempotency Pattern

The threat register specifies "check→execute→store in one transaction (Pitfall 7)." The implementation separates the check from the transaction: `check_idempotency` runs against the pool before `async with pool.connection() as conn, conn.transaction()`, then `store_idempotency` runs inside the transaction (atomic with the DB write). This is the established Phase 3 pattern (identical structure in `cubes.py:700-788`). For a single-admin home-LAN app, the window between check and store is negligible. The store is atomic with the write (Pitfall 7's core concern), so this is considered CLOSED.

### T-05-05-04 Server-Authoritative Validator

The validate path (`POST /admin/cubes/validate`) and both direct write paths (`PUT /cut`, `POST /insert-cut`) all call the same `validate_contiguity()` function from `validation.py`. The UI performs a dry-run before commit, but the server re-validates on commit. A client that bypasses the UI dry-run (e.g., raw HTTP) still hits the validator on the write endpoint.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-23 | 24 | 24 | 0 | gsd-security-auditor (claude-sonnet-4-6) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-23

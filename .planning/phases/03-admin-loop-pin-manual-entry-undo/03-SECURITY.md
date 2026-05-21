---
phase: 3
slug: admin-loop-pin-manual-entry-undo
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-21
---

# Phase 3 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Deployment context: **home LAN only, no public exposure**, single owner + visiting friends.
> Register authored at plan time (all 5 PLANs carried `<threat_model>` blocks) and verified
> against the implemented code by gsd-security-auditor on 2026-05-21.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Browser ↔ API (admin) | Owner's phone/kiosk SPA to FastAPI admin routes | PIN (login only), session cookie, CSRF token, boundary edits |
| Browser ↔ API (public kiosk) | Anyone on the LAN to public read endpoints | Collection metadata (already searchable; non-sensitive) |
| API ↔ Postgres | psycopg pool to `gruvax` schema | Argon2id PIN hash, session rows, boundary_history, idempotency keys |
| API ↔ discogsography view | Read-only `gruvax.v_collection` | Collection records (read-only) |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-03-01 | Tampering | `settings.py` SESSION_SECRET | mitigate | No default — pydantic-settings crashes boot if unset (`settings.py:38`) | closed |
| T-03-02 | DoS | migration 0004 | mitigate | Reversible downgrade, `DROP … IF EXISTS` reverse order | closed |
| T-03-03 | Tampering | catalog comparison | mitigate | `parse_key`/`catalog_in_range` + `.casefold()`; no raw-string compare | closed |
| T-03-04 | Spoofing | PIN brute force | mitigate | Argon2id + `_ctx.verify()`; login rate-limit 5/5min per IP → 429; 4-digit shape gate before hash | closed |
| T-03-05 | Tampering | CSRF on mutating routes | mitigate | Double-submit: `X-CSRF-Token` vs `gruvax_csrf` cookie via `secrets.compare_digest`; client injects header | closed |
| T-03-06 | Info Disclosure | login/change-pin logging | mitigate | PIN never logged — `pin_attempt=redacted` even at DEBUG | closed |
| T-03-07 | EoP | stale/lost-device session | mitigate | idle TTL + hard cap + `revoked_at` checked every request; revoke-others on change-pin | closed |
| T-03-08 | Spoofing | session fixation | mitigate | New UUID session id per login; revoke other sessions on change-pin | closed |
| T-03-09 | Tampering | session cookie forgery | mitigate | `itsdangerous` URLSafeSerializer sign/verify; HttpOnly + SameSite=Strict | closed |
| T-03-10 | Info Disclosure | public cube contents | accept | Intentionally public (D-15); collection already searchable | closed |
| T-03-11 | Tampering | path params unit/row/col | mitigate | FastAPI typed `Path(ge=…)` → 422 on bad input; no f-string SQL | closed |
| T-03-12 | DoS | fill/sample compute | mitigate | In-memory snapshot, no DB during compute | closed |
| T-03-13 | Spoofing/EoP | `/api/admin/cubes/*` | mitigate | `Depends(require_admin)` on all handlers | closed |
| T-03-14 | Tampering | boundary save values | mitigate | Comparator (parse_key) always — even with `force`; phantom check unless force | closed |
| T-03-15 | Tampering | autocomplete source | mitigate | Queries `gruvax.v_collection` only | closed |
| T-03-16 | Tampering | SQL injection (admin) | mitigate | All SQL `%s` placeholders; zero f-string SQL (grep-verified) | closed |
| T-03-17 | Info Disclosure | midpoint suggestion | accept | Returns only already-public record fields | closed |
| T-03-18 | Spoofing/EoP | bulk + revert endpoints | mitigate | `Depends(require_admin)` on both | closed |
| T-03-19 | Tampering | partial commit | mitigate | Single transaction; Idempotency-Key short-circuit | closed |
| T-03-20 | Repudiation | boundary mutations | mitigate | Append-only `boundary_history` (prev/new) source=bulk/revert, inside txn | closed |
| T-03-21 | Tampering | revert clobbering newer edit | mitigate | `has_newer_changes` check → skip + report (no silent clobber) | closed |
| T-03-22 | DoS | stale cache after failed commit | mitigate | `cache.invalidate()+load()` only after txn commits (Pitfall A) | closed |
| T-03-23 | DoS | idempotency_keys growth | mitigate | `cleanup_idempotency` prunes >24h on each bulk | closed |
| T-03-24 | Tampering | SQL in bulk/revert | mitigate | `%s` placeholders only (grep-verified) | closed |
| T-03-SC | Tampering | passlib/limits supply chain | accept | Package legitimacy audited (RESEARCH.md); pinned in pyproject | closed |

*Status: open · closed* — *Disposition: mitigate · accept · transfer*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-03-1 | T-03-10 | Public reveal (fill level + cube contents) is intentional (D-15); the collection is already searchable on the kiosk and LAN-only. | Owner | 2026-05-21 |
| AR-03-2 | T-03-17 | Suggest-midpoint returns only fields already public via search. | Owner | 2026-05-21 |
| AR-03-3 | T-03-SC | `passlib[argon2]` (PyPI-latest) + `limits` are reputable, audited; LAN-only. | Owner | 2026-05-21 |
| AR-03-4 | WR-03 | PinOverlay seeds the countdown from a client-side estimate corrected within 30s by the `/session` poll. **Server enforces all session expiry authoritatively** — client value affects UI display only, not access control. LOW at ASVS L1/LAN. Follow-up: have `POST /login` return `expires_at`/`hard_cap_at` and seed the store from them. | Owner | 2026-05-21 |

*Resolved (no longer open):* **WR-05** (rate-limit proxy comment) and **WR-06** (slowapi private-internals) were fixed on 2026-05-21 — the login rate-limiter was rebuilt on the public `limits` API (`9f6e70b`), removing the slowapi-upgrade fragility on the brute-force guard, and the single-host-LAN key assumption is now documented in code.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-21 | 25 | 25 | 0 | gsd-security-auditor (verify mode) + WR-05/WR-06 remediation |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-21

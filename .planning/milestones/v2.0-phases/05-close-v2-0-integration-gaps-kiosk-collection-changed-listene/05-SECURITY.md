---
phase: 05
slug: close-v2-0-integration-gaps-kiosk-collection-changed-listene
status: verified
threats_open: 0
threats_total: 5
asvs_level: 1
created: 2026-05-30
---

# Phase 05 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| LAN client → /api/search, /api/locate | Untrusted query params (`profile_id`) + `gruvax_browse_binding` / fingerprint cookies cross here | Profile UUID (untrusted), search query string, release ID |
| Backend SSE stream → KioskView EventSource | `collection_changed` server event crosses into the client; payload-less, triggers a cache refetch only | No payload — event name only |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-05-01 | Elevation of Privilege / Information Disclosure | `profile_id` optional on search.py:46 + locate.py:82 | mitigate | `resolve_profile_from_request` called unconditionally at handler entry (search.py:72, locate.py:116) before any data query; effective UUID set to resolver result (not client value); supplied mismatch raises 403 `profile_mismatch` (search.py:79-83, locate.py:123-127); `search_collection` and `get_release_for_locate` receive only `effective_profile_id` (search.py:91, locate.py:140) | closed |
| T-05-02 | Information Disclosure | omitted-param data query path | mitigate | `resolve_profile_from_request` raises 400 `session_unbound` (deps.py:229-232) when no fingerprint and no browse-binding cookie are present — executes before `search_collection` / `get_release_for_locate` is called in both handlers | closed |
| T-05-03 | Information Disclosure | search `useQuery` firing before session bootstrap | mitigate | `enabled: !!boundProfileId && debouncedQuery.trim().length > 0` (KioskView.tsx:171) gates the query on `boundProfileId` non-null; no `/api/search` request is issued while `boundProfileId` is null | closed |
| T-05-04 | Denial of Service | malformed/duplicate `collection_changed` SSE frames | accept | Payload-less handler (KioskView.tsx:340-343) calls only `queryClient.invalidateQueries` and `resync()` — no `JSON.parse`, no new parsing surface; TanStack Query coalesces rapid invalidations; mirrors the accepted `server_hello` pattern | closed |
| T-05-SC | Tampering | npm/pip/cargo installs | accept | No package installs in either plan — pure source edits to existing files; no new dependencies introduced | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-05-01 | T-05-04 | `collection_changed` is payload-less; no `JSON.parse` executed; TanStack Query deduplicates rapid invalidation calls; flood from a compromised server-side publisher has no client-data-corruption surface beyond triggering refetches | Phase 05 executor (autonomous) | 2026-05-30 |
| AR-05-02 | T-05-SC | Phase 05 modifies only existing source files (search.py, locate.py, KioskView.tsx, two test files); no new packages added to pyproject.toml or package.json | Phase 05 executor (autonomous) | 2026-05-30 |

---

## Unregistered Flags

None. Both SUMMARY.md files declare no new trust-boundary surface beyond the registered threats. The Plan 02 SUMMARY notes a test-approach deviation (fetch spy → searchCollection spy) but this is a test-implementation detail with no security surface impact.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-30 | 5 | 5 | 0 | gsd-security-auditor (claude-sonnet-4-6) |

---

## Verification Evidence

| Threat ID | Pattern Verified | File:Line |
|-----------|-----------------|-----------|
| T-05-01 | `profile_id: str \| None = Query(default=None)` | search.py:46, locate.py:82 |
| T-05-01 | `resolved_profile_id, _ = await resolve_profile_from_request(request, pool)` called unconditionally | search.py:72, locate.py:116 |
| T-05-01 | `effective_profile_id = resolved_profile_id` (omitted path) | search.py:76, locate.py:120 |
| T-05-01 | `raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail={"type": "profile_mismatch"})` (supplied mismatch) | search.py:79-83, locate.py:123-127 |
| T-05-01 | `search_collection(pool, q, limit, effective_profile_id)` — client value never passed raw | search.py:91 |
| T-05-01 | `get_release_for_locate(pool, release_id, effective_profile_id)` — client value never passed raw | locate.py:140 |
| T-05-02 | `raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail={"type": "session_unbound"})` — before any data query | deps.py:229-232 |
| T-05-03 | `enabled: !!boundProfileId && debouncedQuery.trim().length > 0` | KioskView.tsx:171 |
| T-05-04 | `es.addEventListener('collection_changed', () => { ... })` — no `JSON.parse`, payload-less | KioskView.tsx:340-343 |
| T-05-04 | Single `es.close()` call preserved (no second teardown added) | KioskView.tsx:347 |
| T-05-SC | No `pip install` / `uv add` / `npm install` / `yarn add` in modified files | grep confirmed clean |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-30

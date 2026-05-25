---
phase: 07-wizards-import-export
reviewed: 2026-05-24T00:00:00Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - src/gruvax/api/admin/import_.py
  - frontend/src/api/adminClient.ts
  - frontend/src/routes/admin/Import.tsx
  - frontend/src/routes/admin/Settings.tsx
  - frontend/src/routes/admin/Wizard.tsx
  - tests/conftest.py
  - tests/integration/test_import.py
  - tests/integration/test_import_roundtrip_identity.py
  - tests/integration/test_locate.py
  - tests/integration/test_migrate_0005.py
findings:
  critical: 1
  warning: 2
  info: 3
  total: 6
status: resolved
resolved_in: 03fb309
---

# Phase 7: Code Review Report

**Reviewed:** 2026-05-24
**Depth:** standard
**Files Reviewed:** 10
**Status:** resolved (CR-01 + WR-01 + WR-02 fixed in `03fb309`; IN-01/02/03 advisory)

## Resolution

- **CR-01 — FIXED** (`03fb309`): `Wizard.tsx` reshuffle resume `Math.min(completedSteps, 0)` → `Math.max(...)`. Verified: frontend tsc+build clean.
- **WR-01 — FIXED** (`03fb309`): settings import write loop wrapped in explicit `conn.transaction()` (matches boundaries path). Verified: `test_settings_import` + full backend suite green.
- **WR-02 — FIXED** (`03fb309`): both export downloads append the `<a>` to the body and defer `remove()`+`revokeObjectURL()` via `setTimeout` (Firefox/Safari + mobile-Safari admin). Verified: frontend tsc+build clean.
- **IN-01/02/03 — advisory, not addressed**: minor docstring staleness, a test-comment gap, and a `source` local-var shadow. Tracked here for a future cleanup pass; no behavioral impact.

## Summary

This review covers the Phase 7 gap-closure changes: dry-run preview and G3 identity-skip in `import_.py`, the frontend import/commit flow in `Import.tsx` and `adminClient.ts`, settings round-trip in `Settings.tsx`, wizard entry-choice and reshuffle-draft resume in `Wizard.tsx`, and the supporting test infrastructure.

The dry-run path cleanly isolates from the DB (no write, no idempotency key minting, no cache invalidation). The G3 identity-skip logic is correct and correctly scoped. The atomic commit uses a proper `conn.transaction()` context. The T-0708-NOOP-COMMIT regression guard is correctly implemented: `runValidation` never stores a commit result and `handleCommit` always posts fresh. No XSS via `innerHTML`, no hardcoded hex. Security controls (CSRF, session, YAML bomb cap, auth.* key exclusion, SQL parameterization) are all in place.

One correctness blocker found: a `Math.min` call in Wizard.tsx that always clamps the restored draft step to 0, breaking reshuffle resume. Two warnings: settings import lacks an explicit transaction wrapper (relying on implicit psycopg rollback), and the download-by-detached-anchor pattern is unreliable in Firefox/Safari. Three info items cover a stale docstring, a test precondition comment gap, and a minor client-side `source` derivation that shadows the server's value.

---

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Wizard reshuffle draft resume always restores step index to 0

**File:** `frontend/src/routes/admin/Wizard.tsx:156`
**Issue:** The `currentStepIndex` initial-state factory contains:
```typescript
if (reshuffleDraft) return Math.min(reshuffleDraft.completedSteps, 0)
```
`Math.min(N, 0)` returns `0` for every non-negative `N`. A reshuffle draft interrupted at step 12 resumes at step 0 instead of step 12 — silently discarding all progress. The user must re-walk every previously completed step. The intent is clearly `Math.max(reshuffleDraft.completedSteps, 0)` (clamp a hypothetically-negative value to 0).

**Fix:**
```typescript
// line 156: change Math.min → Math.max
if (reshuffleDraft) return Math.max(reshuffleDraft.completedSteps, 0)
```

---

## Warnings

### WR-01: `import_settings` writes keys outside an explicit transaction

**File:** `src/gruvax/api/admin/import_.py:711-739`
**Issue:** The settings write loop opens a bare connection and commits at the end:
```python
async with pool.connection() as conn:
    for dotted_key, value in flat_keys.items():
        ...
        await conn.execute("UPDATE gruvax.settings ...", ...)
        updated.append(dotted_key)
    await conn.commit()
```
There is no `async with conn.transaction():` context. If an exception is raised mid-loop (e.g., a psycopg driver error on one UPDATE), the loop exits early, `conn.commit()` is never reached, and psycopg's pool releases the connection with an implicit rollback — so at the DB level, atomicity is preserved accidentally by psycopg 3's default `autocommit=False`. However the "whole-file reject, never partial write" guarantee is implicit: it relies on the driver's connection lifecycle rather than on an explicit transaction block. If the pool is ever configured with `autocommit=True`, or if the pattern is copied to a connection that is already inside a transaction, partial writes become possible. The existing boundaries path correctly uses `async with conn.transaction():`.

**Fix:** Wrap the write loop in an explicit transaction and remove the trailing `conn.commit()`:
```python
async with pool.connection() as conn:
    async with conn.transaction():
        for dotted_key, value in flat_keys.items():
            ...
            await conn.execute("UPDATE gruvax.settings ...", ...)
            updated.append(dotted_key)
        # conn.transaction() commits on clean exit; rolls back on exception
```

---

### WR-02: Download-by-detached-anchor is unreliable in Firefox and Safari

**File:** `frontend/src/api/adminClient.ts:593-601` and `609-621`
**Issue:** Both `downloadBoundariesYaml` and `downloadSettingsYaml` create an anchor element, set `.href` and `.download`, call `.click()`, and immediately revoke the object URL — without appending the element to `document.body`. In Chromium this works. In Firefox, programmatic `.click()` on a detached anchor is treated as an untrusted user gesture and may be ignored. In Safari, the object URL can be revoked before the browser has initiated the fetch. The result is a silent no-op download: no file, no error.

**Fix:**
```typescript
const a = document.createElement('a')
a.href = url
a.download = 'boundaries.yaml'  // or settings.yaml
a.style.display = 'none'
document.body.appendChild(a)
a.click()
setTimeout(() => {
  URL.revokeObjectURL(url)
  document.body.removeChild(a)
}, 150)
```
The `setTimeout` gives the browser a tick to initiate the download before the object URL is revoked. The `appendChild`/`removeChild` ensures the anchor is in the DOM when clicked.

---

## Info

### IN-01: `write_history_row` docstring lists stale Phase 5 source values

**File:** `src/gruvax/db/queries.py:622` (called from `src/gruvax/api/admin/import_.py:502-513`)
**Issue:** The docstring reads: `source must be 'manual', 'bulk', 'revert', or 'cut_insert'`. Migration 0007 extended the DB CHECK to also accept `'wizard'`, `'reshuffle'`, `'csv'`, and `'yaml'`. The import endpoint passes `source='csv'` or `source='yaml'` — both valid at the DB level but absent from the docstring. A developer reading only the function signature would believe `'csv'` is an illegal value.
**Fix:** Update the docstring's source list to include the four Phase 7 values, or reference migration 0007 directly.

---

### IN-02: `test_contiguity_violation` missing comment explaining D-09 empty-fill interaction

**File:** `tests/integration/test_import.py:284-343`
**Issue:** The test uploads 4 cubes for a non-contiguous layout but does NOT seed them as the current boundary first. The D-09 fill will convert every existing DB address absent from the file into `is_empty=True` fills (potentially 28 cubes if a prior test left 32 cubes in the DB). The test works because empty fills do not participate in label contiguity, but this assumption is not stated. If the contiguity validator's treatment of empty fills ever changes, this test would pass for the wrong reason without explanation.
**Fix:** Add a brief comment after the fixture setup: "D-09 fills the remaining DB cubes as is_empty; empty cubes are transparent to the contiguity validator, so only the 4-cube non-contiguous subset triggers the rejection."

---

### IN-03: `handleCommit` derives `source` from filename rather than server response

**File:** `frontend/src/routes/admin/Import.tsx:535-537`
**Issue:** After a successful commit, `source` is derived locally:
```typescript
const ext = state.filename.split('.').pop()?.toLowerCase()
const source = ext === 'csv' ? 'csv' : 'yaml'
```
The server already returns `source` in `CommitResponse` (`import_.py:481`). Using the filename is redundant and silently diverges if a file arrives with an unexpected extension. This is an info-level concern because in practice only `.csv`/`.yaml`/`.yml` reach this point (filtered in `handleFileSelect`), but reading from the server response is more principled.
**Fix:** Prefer `commitData.source` from the server response, with the filename-derived value as a fallback:
```typescript
const source = (commitData.source as string | undefined) ?? (ext === 'csv' ? 'csv' : 'yaml')
```

---

_Reviewed: 2026-05-24_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

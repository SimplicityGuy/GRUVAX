---
phase: quick
plan: 260602-oxg
type: execute
wave: 1
depends_on: []
files_modified:
  - frontend/src/routes/kiosk/KioskView.tsx
  - frontend/src/routes/admin/ShelfBinList.tsx
  - frontend/src/routes/admin/ShelfBinList.sse.test.tsx
  - .planning/phases/06-safe-boundaries-live-device-lifecycle/06-01-SUMMARY.md
  - .planning/phases/06-safe-boundaries-live-device-lifecycle/06-02-SUMMARY.md
  - .planning/phases/06-safe-boundaries-live-device-lifecycle/06-03-SUMMARY.md
  - .planning/phases/07-member-self-connect-collection-diff/07-02-SUMMARY.md
  - .planning/phases/08-qr-pairing-privacy-recently-pulled/08-01-SUMMARY.md
  - .planning/phases/08-qr-pairing-privacy-recently-pulled/08-02-SUMMARY.md
  - .planning/phases/08-qr-pairing-privacy-recently-pulled/08-03-SUMMARY.md
  - .planning/phases/09-offline-reconnect-ux/09-01-SUMMARY.md
  - .planning/phases/09-offline-reconnect-ux/09-02-SUMMARY.md
  - .planning/phases/09-offline-reconnect-ux/09-03-SUMMARY.md
  - .planning/phases/09-offline-reconnect-ux/09-04-SUMMARY.md
  - .planning/phases/09-offline-reconnect-ux/09-05-SUMMARY.md
  - .planning/phases/10-shelf-fill-overview/10-01-SUMMARY.md
  - .planning/phases/10-shelf-fill-overview/10-02-SUMMARY.md
autonomous: true
requirements: [OFF-04, DOCS]

must_haves:
  truths:
    - "KioskView no longer fires the dead ['admin','settings'] invalidation on server_hello; resync() still runs"
    - "Admin ShelfBinList fill shading refreshes after a server restart (server_hello invalidates ['admin','cubes'])"
    - "Every in-scope SUMMARY.md declares requirements-completed (REQ-IDs or an explicit infra/test-only note)"
  artifacts:
    - path: "frontend/src/routes/kiosk/KioskView.tsx"
      provides: "server_hello handler with only resync()"
      contains: "addEventListener('server_hello'"
    - path: "frontend/src/routes/admin/ShelfBinList.tsx"
      provides: "server_hello listener invalidating ['admin','cubes']"
      contains: "addEventListener('server_hello'"
    - path: "frontend/src/routes/admin/ShelfBinList.sse.test.tsx"
      provides: "Test 3: server_hello invalidates [admin, cubes]"
      contains: "server_hello"
  key_links:
    - from: "frontend/src/routes/admin/ShelfBinList.tsx"
      to: "['admin','cubes']"
      via: "server_hello EventSource listener → queryClient.invalidateQueries"
      pattern: "server_hello"
---

<objective>
Close the three non-blocking v2.1 milestone tech-debt warnings from `.planning/v2.1-MILESTONE-AUDIT.md`:

1. WARNING-1 (OFF-04): remove the dead `['admin','settings']` invalidation in KioskView's `server_hello` handler.
2. WARNING-2: admin ShelfBinList fill shading goes stale after a server restart — add a `server_hello` listener that invalidates `['admin','cubes']`, plus a mirroring test.
3. Item D (docs): backfill the `requirements-completed` frontmatter field across the in-scope phase SUMMARY.md files.

Purpose: clean accumulated non-blocking debt before archiving the v2.1 milestone. No behavior change beyond the two specified fixes.
Output: two small frontend edits, one new test, and frontmatter backfill across 14 SUMMARY files.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/v2.1-MILESTONE-AUDIT.md
@./CLAUDE.md

<interfaces>
From frontend/src/routes/admin/ShelfBinList.tsx (useAdminCubesInvalidation, ~lines 56-79):
The hook opens `new EventSource(/api/events/${profileId})` and registers two listeners that each call
`void queryClient.invalidateQueries({ queryKey: ['admin', 'cubes'] })` for `collection_changed` and `boundary_changed`.
Cleanup closes the EventSource on unmount (`return () => es.close()`).

From frontend/src/routes/kiosk/KioskView.tsx (~lines 405-409):
The `server_hello` listener calls `resync()` then `void queryClient.invalidateQueries({ queryKey: ['admin', 'settings'] })`.
Settings.tsx loads via useEffect + getAdminSettings (NOT useQuery), so nothing subscribes to ['admin','settings'] —
the invalidation is a confirmed no-op.

Frontend test runner (frontend/package.json): `npm --prefix frontend run test` → `vitest run`.
A single file can be targeted with `npm --prefix frontend run test -- ShelfBinList.sse`.

ShelfBinList.sse.test.tsx existing structure: a `MockEventSource` (stubbed globally) with `dispatchEvent(name, data)`,
a `renderShelfBinListAndFlush(qc)` helper returning `{ es, unmount }`, and `vi.spyOn(qc, 'invalidateQueries')` to
assert `calledKeys` contains `['admin','cubes']`. Mirror Test 1 / Test 2 exactly.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Remove dead ['admin','settings'] invalidation in KioskView (WARNING-1 / OFF-04)</name>
  <files>frontend/src/routes/kiosk/KioskView.tsx</files>
  <action>
In the `server_hello` event listener (~line 406-409), DELETE the single line
`void queryClient.invalidateQueries({ queryKey: ['admin', 'settings'] })`.
Keep the `resync()` call as the only statement in the handler body.
Update the adjacent comment if it still references "+ settings" so it reads as resync-only
(e.g. "server_hello: server (re)started → resync all data"). Do NOT touch any other listener,
do NOT remove the `queryClient` binding (it is used elsewhere in this file). No other changes.
Rationale: Settings.tsx loads via useEffect+getAdminSettings, not useQuery, so nothing subscribes
to ['admin','settings'] — confirmed no-op. No test asserts this invalidation.
  </action>
  <verify>
    <automated>cd frontend && grep -A3 "addEventListener('server_hello'" src/routes/kiosk/KioskView.tsx | grep -q "resync()" && ! grep -q "queryKey: \['admin', 'settings'\]" src/routes/kiosk/KioskView.tsx && npx tsc -b --noEmit</automated>
  </verify>
  <done>The `['admin','settings']` invalidation line is gone, `resync()` remains in the server_hello handler, and `tsc` is clean.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add server_hello → ['admin','cubes'] invalidation in ShelfBinList + Test 3 (WARNING-2)</name>
  <files>frontend/src/routes/admin/ShelfBinList.tsx, frontend/src/routes/admin/ShelfBinList.sse.test.tsx</files>
  <behavior>
    - Test 3: dispatching a `server_hello` event on the admin MockEventSource calls
      `queryClient.invalidateQueries` with queryKey `['admin','cubes']`.
    - Existing Test 1 (collection_changed), Test 2 (boundary_changed), the unmount/close test,
      and the null-profileId test all still pass.
  </behavior>
  <action>
In `frontend/src/routes/admin/ShelfBinList.tsx`, inside `useAdminCubesInvalidation` (~lines 65-73),
ADD a third listener alongside the existing `collection_changed` and `boundary_changed` ones:
`es.addEventListener('server_hello', () => { void queryClient.invalidateQueries({ queryKey: ['admin', 'cubes'] }) })`.
Use the identical handler body as the other two. Place it after the `boundary_changed` listener and before
the cleanup return. Add a short comment noting this refreshes fill shading after a server restart
(WARNING-2, v2.1 milestone audit). Do not change the EventSource URL, the early-return guard, or the cleanup.

Then in `frontend/src/routes/admin/ShelfBinList.sse.test.tsx`, ADD "Test 3: server_hello invalidates [admin, cubes]"
inside the existing `describe('ShelfBinList SSE invalidation ...')` block, mirroring Test 1 / Test 2: create a
QueryClient via `makeQueryClient()`, spy with `vi.spyOn(qc, 'invalidateQueries')`, render via
`renderShelfBinListAndFlush(qc)`, then `await act(async () => { es.dispatchEvent('server_hello', {}) })`, and assert
`calledKeys` contains `['admin','cubes']`. The file header comment block (lines 7-9) may be updated to mention the
new server_hello test — keep it accurate but do not overhaul it. Do not rename/renumber the existing close and
null-profileId tests' assertions.
  </action>
  <verify>
    <automated>cd frontend && npm run test -- ShelfBinList.sse</automated>
  </verify>
  <done>ShelfBinList.tsx has a `server_hello` listener invalidating `['admin','cubes']`; the new Test 3 plus all pre-existing tests in ShelfBinList.sse.test.tsx pass.</done>
</task>

<task type="auto">
  <name>Task 3: Backfill requirements-completed frontmatter in phase SUMMARYs (item D)</name>
  <files>.planning/phases/06-safe-boundaries-live-device-lifecycle/06-01-SUMMARY.md, .planning/phases/06-safe-boundaries-live-device-lifecycle/06-02-SUMMARY.md, .planning/phases/06-safe-boundaries-live-device-lifecycle/06-03-SUMMARY.md, .planning/phases/07-member-self-connect-collection-diff/07-02-SUMMARY.md, .planning/phases/08-qr-pairing-privacy-recently-pulled/08-01-SUMMARY.md, .planning/phases/08-qr-pairing-privacy-recently-pulled/08-02-SUMMARY.md, .planning/phases/08-qr-pairing-privacy-recently-pulled/08-03-SUMMARY.md, .planning/phases/09-offline-reconnect-ux/09-01-SUMMARY.md, .planning/phases/09-offline-reconnect-ux/09-02-SUMMARY.md, .planning/phases/09-offline-reconnect-ux/09-03-SUMMARY.md, .planning/phases/09-offline-reconnect-ux/09-04-SUMMARY.md, .planning/phases/09-offline-reconnect-ux/09-05-SUMMARY.md, .planning/phases/10-shelf-fill-overview/10-01-SUMMARY.md, .planning/phases/10-shelf-fill-overview/10-02-SUMMARY.md</files>
  <action>
For each in-scope SUMMARY.md, add (or populate) a `requirements-completed:` frontmatter field, mirroring the format
in 07-01-SUMMARY.md (`requirements-completed: [API-04]`) and 07-03-SUMMARY.md (`requirements-completed: [AUTH-02, API-04]`).
NOTE: in the in-scope files the field is currently ABSENT, not present-but-empty — add it inside the YAML frontmatter
(between `---` fences), placed consistently (e.g. just after the last dependency/tech-tracking block, before any
`# Metrics`/`duration` section, matching where 07-01 places it). Leave 07-01 and 07-03 untouched (already populated).

Sourcing rule per file:
1. Read the owning phase's `{phase}-VERIFICATION.md` (e.g. `06-VERIFICATION.md`) requirement-traceability table to
   map each plan to the REQ-IDs it delivered.
2. Cross-check against the plan's own `provides:`/scope in its SUMMARY frontmatter.
3. Set `requirements-completed: [REQ-ID, ...]` listing only the end-user requirements that specific plan delivered.
4. If a plan delivered NO end-user requirement (pure test/infra/scaffold plan — e.g. a test-only plan like 06-03),
   set `requirements-completed: []` and add a brief inline note that it is infra/test-only
   (e.g. `requirements-completed: []  # test/infra-only plan; coverage tracked in 06-VERIFICATION.md`).
Do NOT invent REQ-IDs that the VERIFICATION table does not attribute to that plan. Do not edit any other frontmatter
field or body content.
  </action>
  <verify>
    <automated>for f in .planning/phases/06-*/0*-SUMMARY.md .planning/phases/07-*/07-02-SUMMARY.md .planning/phases/08-*/0*-SUMMARY.md .planning/phases/09-*/0*-SUMMARY.md .planning/phases/10-*/1*-SUMMARY.md; do grep -q "^requirements-completed:" "$f" || echo "MISSING: $f"; done; echo scan-done</automated>
  </verify>
  <done>All 14 in-scope SUMMARY.md files declare `requirements-completed` (a REQ-ID list, or `[]` with an infra/test-only note); 07-01 and 07-03 left unchanged; the scan prints only `scan-done` (no MISSING lines).</done>
</task>

</tasks>

<verification>
- `npm --prefix frontend run test` passes (all suites, including the new Test 3).
- `npx tsc -b --noEmit` from `frontend/` is clean.
- Grep confirms KioskView server_hello handler retains `resync()` and no longer contains `['admin','settings']`.
- Grep confirms ShelfBinList contains a `server_hello` listener.
- No in-scope SUMMARY.md is missing the `requirements-completed` field.
</verification>

<success_criteria>
- WARNING-1 resolved: dead `['admin','settings']` invalidation removed; resync() preserved; tsc clean.
- WARNING-2 resolved: admin fill shading invalidates `['admin','cubes']` on `server_hello`, covered by passing Test 3.
- Item D resolved: all 14 in-scope SUMMARYs carry a populated (or explicitly noted infra/test-only) `requirements-completed` field, sourced from each phase's VERIFICATION traceability table.
- No behavior change beyond the two specified fixes; no invented REQ-IDs.
</success_criteria>

<output>
Create `.planning/quick/260602-oxg-close-v2-1-milestone-tech-debt-warning-1/260602-oxg-SUMMARY.md` when done.
</output>

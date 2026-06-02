---
phase: 10
slug: shelf-fill-overview
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-02
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Vitest (frontend component/unit tests) + tsc/eslint/build static gates |
| **Config file** | `frontend/vitest.config.ts` (existing) |
| **Quick run command** | `npm --prefix frontend run test -- <scope>` |
| **Full suite command** | `npm --prefix frontend run test && npm --prefix frontend run -s exec tsc -- --noEmit && npm --prefix frontend run lint && npm --prefix frontend run build` |
| **Estimated runtime** | ~60 seconds (quick scoped run ~5s) |

---

## Sampling Rate

- **After every task commit:** Run scoped `npm --prefix frontend run test -- <scope>`
- **After every plan wave:** Run the full suite command
- **Before `/gsd:verify-work`:** Full suite (test + tsc + lint + build) must be green
- **Max feedback latency:** ~60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 1 | UX-01 | — | N/A (type-only) | static | `grep -q record_count frontend/src/api/types.ts && (cd frontend && npx tsc --noEmit)` | ✅ | ⬜ pending |
| 10-01-02 | 01 | 1 | UX-01 | — | N/A (RED tests) | unit | `npm --prefix frontend run test -- LocatorHeader` | ❌ W0 | ⬜ pending |
| 10-01-03 | 01 | 1 | UX-01 | T-10-01 | Counts/labels rendered as React text (no dangerouslySetInnerHTML) | component | `npm --prefix frontend run test -- LocatorHeader` | ✅ | ⬜ pending |
| 10-02-01 | 02 | 2 | UX-01 | — | N/A (RED SSE tests) | unit | `npm --prefix frontend run test -- ShelfBinList.sse` | ❌ W0 | ⬜ pending |
| 10-02-02 | 02 | 2 | UX-01 | — | Same-origin admin SSE; read-only event-driven invalidation; es.close() on unmount | component | `npm --prefix frontend run test -- ShelfBinList` | ✅ | ⬜ pending |
| 10-02-03 | 02 | 2 | UX-01 | — | Full static gate | gate | `npm --prefix frontend run test && (cd frontend && npx tsc --noEmit) && npm --prefix frontend run lint && npm --prefix frontend run build` | ✅ | ⬜ pending |
| 10-02-04 | 02 | 2 | UX-01 | — | N/A (human UAT on 7" kiosk) | manual | `<human-check>` | — | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `frontend/src/routes/admin/LocatorHeader.test.tsx` — RED tests for fill shading, empty state, clamp, lit-priority, tap popover (created in 10-01 Task 2 before GREEN impl)
- [ ] `frontend/src/routes/admin/ShelfBinList.sse.test.tsx` — RED tests for `collection_changed` + `boundary_changed` invalidation and unmount cleanup (created in 10-02 Task 1)
- [ ] No framework install needed — Vitest infrastructure already present

*Test files are created in-plan via TDD RED→GREEN; no separate Wave 0 plan required.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Empty vs. full cube obviously distinct at a glance at 28px on the 7" kiosk | UX-01 SC3 | Glanceability is a perceptual judgment that automated assertions cannot prove | On the kiosk/admin display, open ShelfBinList; confirm an empty bin (gray/dashed CUBE-05) and a full bin (deepest blue) are instantly distinguishable without reading numbers |
| Live reshade after a real sync without page reload | UX-01 SC2 | End-to-end SSE + sync is environment-dependent | Trigger a sync (or boundary edit); confirm LocatorHeader cubes reshade with no page reload |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (RED test files created in-plan)
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-02

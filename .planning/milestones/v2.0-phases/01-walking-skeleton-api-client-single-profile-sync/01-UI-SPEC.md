---
phase: 1
slug: walking-skeleton-api-client-single-profile-sync
status: draft
shadcn_initialized: false
preset: none
created: 2026-05-26
---

# Phase 1 — UI Design Contract

> Walking skeleton — API client + single-profile sync. **Backend-heavy phase.** Two visible UI deltas only; no new screens, no new components, no new routes. This spec codifies the two existing surfaces' contracts under the new data source.

---

## Scope (UI-only delta vs. v1.0)

| # | Surface | What changes in P1 | What stays the same |
|---|---------|--------------------|---------------------|
| 1 | `/api/health` `discogsography_*_check` field | **Field rename** + **state widening**: `discogsography_view_check: 'ok' \| 'failed'` → `discogsography_api_check: 'ok' \| 'failed' \| 'stale'` (D-13). Derived from `last_sync_status`, `app_token_revoked`, and `now() - profiles.last_sync_at` for the default profile. No live HTTP probe per request. | Endpoint path (`GET /api/health`), HTTP status (always 200), the `status: 'ok' \| 'degraded'` overall field, and the `sync_age_seconds` field shape (still float\|null). |
| 2 | Kiosk staleness banner (`StalenessBar`) | **Data source only**: `sync_age_seconds` is now derived server-side from `now() - profiles.last_sync_at` for the single default profile (UUID `00000000-0000-0000-0000-000000000001`), replacing `max(v_collection.synced_at)` (CON-staleness-redefinition). | Component file (`frontend/src/routes/kiosk/StalenessBar.tsx`), trigger threshold (`> 14 days = 1_209_600 s`, D-01 v1.0), banner copy, styling, animation, accessibility, role/aria contract — **all unchanged**. |

**Out of scope (defer):**
- Per-profile staleness fan-out → P2 (SYN-02 multi-profile)
- Per-profile diagnostics cards + 401 reauth UI + "Sync now" progress toast → P4
- Profile picker / profile manager UI → P2/P3
- Any new admin surface for `gruvax-set-pat` or `gruvax-sync` CLIs (they are CLI-only in P1, D-07/D-10)

---

## Design System

No change from v1.0 — see `design/gruvax-design-language.md`.

| Property | Value | Source |
|----------|-------|--------|
| Tool | none (vanilla React + DOM via `el()` / `replaceChildren()`) | inherited from v1.0 |
| Preset | not applicable | n/a |
| Component library | none — project-native components (StalenessBar already exists) | `frontend/src/routes/kiosk/StalenessBar.tsx` |
| Icon library | inline SVG (Lucide subset, hand-authored) | v1.0 Phase 8 pattern |
| Token source | `design/gruvax-design-tokens.css` — consume only; never hardcode hex | mandated by `CLAUDE.md` |
| Fonts | Barlow Condensed (700/900) · Space Grotesk (400/500/700) · DM Mono (400/500) | unchanged |

**Build constraint:** consume `gruvax-design-tokens.css` only; never hardcode hex. Vanilla DOM via `el()` + `replaceChildren()`; never `innerHTML`. (Both invariants inherited from v1.0 Phase 5/8/9.)

---

## Spacing Scale

No change from v1.0 — see `design/gruvax-design-language.md` §Spacing scale.

The only spacing tokens consumed by the P1 banner surface are the existing v1.0 Phase 8 selections:

| Token | Value | Usage in P1 (StalenessBar) |
|-------|-------|----------------------------|
| `--gruvax-space-2` | 8px | Icon ↔ text gap inside the banner |
| `--gruvax-space-3` | 12px | Banner vertical padding |
| `--gruvax-space-4` | 16px | Banner horizontal padding |

Exceptions: none.

---

## Typography

No change from v1.0 — see `design/gruvax-design-language.md` §Typography.

P1 introduces no new type roles. The single typographic element in scope is the banner message string:

| Role | Family | Size token (px) | Weight | Line height | Where |
|------|--------|-----------------|--------|-------------|-------|
| Kiosk banner copy | Space Grotesk | `--gruvax-text-body-lg` (18px) | 400 | `--gruvax-leading-normal` (1.5) | `StalenessBar` message ONLY — 18px is the WCAG-large-text floor for the yellow-on-dark-blue contrast (~3.1:1) |

Enforcement: 18px stays reserved exclusively for this banner across the kiosk view (v1.0 Phase 8 §Typography rule carries forward). No P1 work introduces a 5th or 6th size.

---

## Color

No change from v1.0 — see `design/gruvax-design-language.md` §Color and `gruvax-design-tokens.css`.

### Banner color contract (unchanged from v1.0 Phase 8 Surface 2)

| Role | Token | Hex (for context) | Usage in P1 |
|------|-------|-------------------|-------------|
| Dominant surface (60%) | `--gruvax-off-white` / `--gruvax-white` | #F7F9FC / #FFFFFF | Kiosk page background (unchanged) |
| Secondary surface (30%) | `--gruvax-blue-light` | #D8E8F5 | Dim cube fill (unchanged) |
| Accent (10%) | `--gruvax-yellow` | #FFDA00 | Lit cube + **staleness banner background** (the banner is one of the two `accent` consumers in the kiosk view) |
| Banner text | `--gruvax-blue-darker` | #002855 | Banner foreground — 3.1:1 on yellow at 18px, WCAG large-text pass |
| Destructive | `--gruvax-error` | #C0392B | Not used in P1 (no destructive actions on this surface) |

**Accent reserved for:** (a) lit/found cubes (LED metaphor), (b) the kiosk staleness banner background when `sync_age_seconds > 14d`. No other yellow usage in P1.

### `/api/health` state → kiosk surface mapping

The new `discogsography_api_check` field (D-13) is **not directly rendered** in P1. The kiosk continues to read `sync_age_seconds` to drive the banner. The three-state field exists so P4 can derive the per-profile reauth-required badge from `app_token_revoked = TRUE` without changing the staleness banner. P1 only proves the wire contract is in place.

| `discogsography_api_check` value | Server-side derivation | UI consequence in P1 | UI consequence in P4 (preview, deferred) |
|----------------------------------|------------------------|----------------------|-------------------------------------------|
| `ok` | `last_sync_status = 'ok'` AND `app_token_revoked = FALSE` | None (banner driven by `sync_age_seconds`) | "OK" badge in profile-list admin UI |
| `failed` | `last_sync_status = 'failed'` OR `app_token_revoked = TRUE` | None in P1 (no failed-sync UI affordance) | 401 reauth banner on kiosk + reauth-required badge in admin (P4 SYN-02 polish) |
| `stale` | `last_sync_at IS NULL` OR `now() - last_sync_at > 24h` | None in P1 (the kiosk `> 14d` banner is a separate, more permissive threshold) | "STALE" pill on admin diagnostics card |

**Invariant (P1):** the kiosk staleness banner trigger remains `sync_age_seconds > 14 days` — the new `stale` state's 24h threshold is an **operator-facing** signal surfaced via `/api/health`, not a user-facing banner trigger. (The owner sees "your PAT hasn't synced since this morning" in admin; the visiting friend at the kiosk doesn't see a yellow banner until 14 full days have passed.)

---

## Copywriting Contract

No change from v1.0 Phase 8 §Copywriting.

| Element | Copy (exact) | Source |
|---------|--------------|--------|
| Primary CTA | n/a — no new CTAs in P1 (admin actions live in CLIs `gruvax-set-pat` / `gruvax-sync` per D-07/D-10) | — |
| Kiosk staleness banner | `Collection data may be outdated — last synced {Xd} ago` | v1.0 Phase 8 Surface 2 (verbatim) |
| Empty state | n/a — no new empty states in P1 | — |
| Error state | n/a — no new user-facing error surfaces in P1 (PAT rejection surfaces in `gruvax-set-pat` CLI stderr per D-08, not in UI) | — |
| Destructive confirmation | n/a — no destructive actions on the kiosk banner; CLI-only profile mutation in P1 | — |

**Voice rules (inherited from v1.0):**
- Sentence case for banner copy (Space Grotesk 400) — already conformant in `StalenessBar.tsx`.
- Plain language: no "sync_age_seconds", no "profile_collection", no "PAT", no "Fernet" appears in any user-visible string. (CLI stderr strings per D-09 are operator-facing, not UI-facing, and explicitly may use technical vocabulary like "discogsography user".)
- Em dash separator preserved verbatim — "last synced" ↔ "{Xd} ago".

**Day-count formatting:** `{Xd}` = whole days only (`Math.floor(syncAgeSeconds / 86400)`), e.g. `18d`, `22d`, `30d`. No hours suffix on the kiosk banner. Unchanged from v1.0.

---

## Component Inventory

P1 introduces zero new frontend components. Modified files:

| File | Change | Driver |
|------|--------|--------|
| `frontend/src/routes/kiosk/StalenessBar.tsx` | **No change.** Props (`syncAgeSeconds: number \| null`), render output, ARIA, CSS — all preserved. | Banner data source changes server-side; the wire contract (`/api/health.sync_age_seconds`) is unchanged. |
| `frontend/src/routes/kiosk/StalenessBar.css` | **No change.** | — |
| `frontend/src/routes/kiosk/StalenessBar.test.tsx` | Add test case asserting banner still triggers when `sync_age_seconds = 1_209_700` (just over 14d) with the new server-derivation path. Existing test cases pass unchanged. | Regression safety on the data-source swap. |
| `frontend/src/routes/kiosk/KioskView.tsx` | **No change.** TanStack Query against `/api/health` and the 60s `refetchInterval` (existing) continue to drive the banner. | The kiosk consumes `sync_age_seconds`, not the new `discogsography_api_check` field. |
| `frontend/src/routes/admin/Diagnostics.tsx` | **No change in P1.** The `formatSyncAge()` and `stalenessStatus()` helpers continue to read `data.sync_age_seconds` from the same endpoint. The page label "DISCOGSOGRAPHY LAST SYNC" remains accurate (the value's *source* changed; the *meaning* didn't). | Per-profile fan-out + per-profile cards land in P4. |
| `frontend/src/api/types.ts` (or wherever `HealthResponse` is typed) | **Rename** field type member `discogsography_view_check` → `discogsography_api_check`; widen union from `'ok' \| 'failed'` to `'ok' \| 'failed' \| 'stale'`. No consumers of the field exist in v1.0 frontend code (verified — no grep hits outside the test fixture), so the rename is a type-only delta. | D-13 contract change. |

**Contract note for the planner / executor:** if any frontend code path is later found to consume `discogsography_view_check`, rewire it to `discogsography_api_check` in the same plan that ships the backend rename. No backward-compatibility shim — this is a same-deployment migration, not a public API.

---

## Accessibility

No change from v1.0 — see `design/gruvax-design-language.md` §Accessibility.

The single accessible surface in P1 is the banner, and its existing contract holds:

- **Contrast:** `--gruvax-blue-darker` (#002855) on `--gruvax-yellow` (#FFDA00) ≈ 3.1:1 → meets WCAG AA for large text (≥18px regular or ≥14px bold). The 18px Space Grotesk 400 banner copy clears the floor.
- **Role + live region:** `role="alert"` + `aria-live="polite"` on mount (announces once, no re-announce on every render). Unchanged.
- **Icon:** decorative `<svg aria-hidden="true">` — not a load-bearing affordance. Unchanged.
- **Persistence:** non-dismissible (operational signal, not a notification). Unchanged.
- **Keyboard:** banner is not focusable (informational, not interactive). Unchanged.

---

## Animation / Motion

No change from v1.0 — see `design/gruvax-design-language.md` §Animation and `StalenessBar.css`.

| Transition | Duration | Easing | Token | Trigger |
|------------|----------|--------|-------|---------|
| Banner enter | 250ms | decelerate (`cubic-bezier(0.0, 0.0, 0.2, 1)`) | `--gruvax-duration-base` × `--gruvax-ease-decelerate` | Component mount (opacity 0→1, max-height 0→48px) |
| Banner exit | Implicit (React unmount) | — | — | `syncAgeSeconds <= 14d \|\| null` (component returns `null`) |

P1 does NOT add a "syncing now" pulse, a "PAT rejected" shake, or any other new motion. Those are P4 surfaces.

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| n/a (no component registry in this project) | none | not applicable |

No shadcn, no third-party registries. Frontend is vanilla React 19 + GSAP + Framer Motion + project-native components. No P1 work introduces a new dependency.

---

## Verification Checklist

P1 UI is correct when:

- [ ] `discogsography_api_check` appears in `/api/health` JSON with values strictly ∈ `{'ok', 'failed', 'stale'}`; `discogsography_view_check` no longer appears.
- [ ] `HealthResponse` TypeScript type renamed and re-narrowed; `tsc --noEmit` passes.
- [ ] Kiosk staleness banner renders identical pixels (background, text color, padding, icon, copy, animation) as v1.0 when `sync_age_seconds > 1_209_600`.
- [ ] When the default profile has `last_sync_at = now() - 15 days`, `sync_age_seconds = 1_296_000` and the banner reads "Collection data may be outdated — last synced 15d ago".
- [ ] When the default profile has `last_sync_at = NULL` (never synced — fresh deployment before first `gruvax-sync`), `sync_age_seconds = null` and the banner is hidden (offline-banner-leads semantics carry over).
- [ ] `discogsography_api_check = 'stale'` (sync >24h old) does NOT trigger the kiosk banner — the 14d threshold is the single banner trigger in P1.
- [ ] No new strings appear in user-visible UI; no new components are exported from `frontend/src/routes/kiosk/` or `frontend/src/routes/admin/`.
- [ ] Token consumption: zero hardcoded hex anywhere in modified CSS/TSX.

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS (no new copy; v1.0 banner string verbatim)
- [ ] Dimension 2 Visuals: PASS (no new visual elements; banner unchanged)
- [ ] Dimension 3 Color: PASS (60/30/10 inherited; accent reserved-for list unchanged)
- [ ] Dimension 4 Typography: PASS (no new type roles; 18px floor for banner preserved)
- [ ] Dimension 5 Spacing: PASS (existing space-2/3/4 tokens; all multiples of 4)
- [ ] Dimension 6 Registry Safety: PASS (no registries in use)

**Approval:** pending

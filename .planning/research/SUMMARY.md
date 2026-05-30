# Project Research Summary

**Project:** GRUVAX v2.1 — Resilience + Privacy + UX Polish
**Domain:** Subsequent milestone — household vinyl-locator kiosk (shipped Python/FastAPI + React)
**Researched:** 2026-05-30
**Confidence:** HIGH

## Executive Summary

GRUVAX v2.1 is a tightly scoped subsequent milestone that adds household-member self-connect (AUTH-02), QR+PIN dual-mode device pairing (DEV-04), collection diff highlighting (API-04), session-only recently-pulled list (SRCH-09), offline/reconnect UX (OFF-01..04), query-privacy enforcement (PRIV-01..04), shelf fill-overview polish, and two v2.0 tech-debt closures (DEV-02 SSE fan-out + write_boundary profile scoping). The research consensus across all four domains is that the stack delta is minimal — one new frontend package (`react-qr-code` 2.0.21), one new Alembic migration (0012: `invite_redemptions` table + `profiles.prev_sync_item_count` column), and new uses of primitives already in the project (`itsdangerous.URLSafeTimedSerializer`, `sessionStorage`, TanStack Query `networkMode`, native `EventSource` reconnect). No new backend Python packages. No service worker.

The hard architectural constraint that shapes every phase decision is that the two tech-debt items — `write_boundary` missing `profile_id` in its WHERE clause, and the kiosk SSE consumer not handling `device_revoked` / `device_reassigned` events — must be fixed before any feature work lands. The `write_boundary` gap is a latent multi-profile data-integrity hazard; any boundary-editing UI that operates in a multi-profile context will silently corrupt the wrong profile's boundaries until this is closed. The DEV-02 SSE gap means the offline UX cannot correctly handle the terminal device-revoke case. Both fixes are pure code changes (no migration), and together they constitute the mandatory Wave 1.

The critical security posture for AUTH-02 is non-negotiable: invite tokens must use a URL path segment (not `?token=` query param) to prevent referrer and Uvicorn access-log leakage; they must be single-use enforced via the `invite_redemptions` DB table (the signed token alone is not sufficient); the member's PAT must be validated against discogsography before storage; and the `ProfileResponse` schema must never expose `app_token_encrypted` — only a `has_token: bool` derived field. There are four critical pitfalls in this one feature cluster alone. The QR pairing has its own pre-implementation decision that must be made: whether to accept HTTP + short-TTL nonce (recommended for home LAN threat model) or add a confirmation step, before any code is written.

## Key Findings

### Recommended Stack

v2.1 introduces essentially no new stack surface. All backend additions draw from dependencies already in the lockfile: `itsdangerous.URLSafeTimedSerializer` (already present as a transitive dep of `starlette.SessionMiddleware`) handles signed invite tokens; `sessionStorage` (browser built-in) handles session-only search history and recently-pulled; TanStack Query's `networkMode: 'offlineFirst'` (already in use, configuration change only) and a ~25-line custom `useBackendOnline` hook using `/healthz` (already shipped in v1.0) handle offline detection. The frontend adds one package.

**Core net-new additions:**

- `react-qr-code` 2.0.21 (frontend only): Pure SVG QR generation; actively maintained (last publish 2026-04-29); zero runtime dependencies. The alternative `qrcode.react` was last published 2024-12-11 and is effectively unmaintained.
- `itsdangerous.URLSafeTimedSerializer` + `invite_redemptions` table: Signed, time-limited invite URLs from a dependency already in the lockfile; DB table enforces single-use since the signed token alone cannot prevent replay within TTL.
- TanStack Query `networkMode` config + custom `useBackendOnline` hook: `navigator.onLine` is unreliable on a home LAN (reflects "has a network interface," not "can reach GRUVAX server"); the healthz-based hook is the correct signal.
- `sessionStorage` (built-in): Session-scoped, auto-cleared on Chromium restart, adequate for 10–20 recent search strings. `localStorage` violates PRIV-01; Zustand `persist` middleware's default `localStorage` target is the trap to avoid.

**Explicit exclusions confirmed by research:**
- No `vite-plugin-pwa` / Workbox: service workers complicate SSE, solve "full offline" (not GRUVAX's problem).
- No `PyJWT` / `python-jose` / `authlib` / `fastapi-users`: `itsdangerous` already present covers the invite-token use case.
- No `python-qrcode` / server-side QR: the kiosk owns the pairing URL and can render client-side with less complexity.
- No `idb` / `localforage` / `dexie`: IndexedDB is wrong scope for a small session-only list.

### Expected Features

**Must ship for v2.1 milestone:**

- AUTH-02 invite-token flow: owner generates per-profile link; member pastes their own PAT; profile connects without owner handling the credential.
- DEV-04 QR + PIN dual-mode on pairing screen: QR is additive; both paths call the same `complete_pairing()` function; neither replaces the other.
- API-04 collection diff count: `new_count` in `collection_changed` SSE payload + count badge in admin. Backed by `profiles.prev_sync_item_count` column (migration 0012). Diff based on `discogs_added_at`, not `cache_added_at` (prevents spurious inflation during sync-gap catchup).
- SRCH-09 recently-pulled + PRIV-04 kiosk reset: ship together — reset must clear the recently-pulled list. Session-only storage; no server-side persistence.
- OFF-01..04 offline/reconnect UX: SSE connection state as primary signal (not `navigator.onLine`); offline banner; search disabled while offline (but last result persists); exponential backoff reconnect (1s→2s→4s→8s→30s cap); "Back online" success flash; TanStack Query invalidation on reconnect.
- PRIV-01..03 privacy: structlog pipeline processor redacts `query` field; Uvicorn access log disabled in production; no `search_log` table; CI assertion that search terms do not appear in `docker logs` output.
- Shelf fill-overview (ex-999.1): `fill_level` field on `GET /api/admin/cubes` response; `LocatorHeader` mini-Kallax renders fill shading using existing design tokens.
- DEV-02 + write_boundary scoping: tech-debt closure; must land first.

**Defer to v2.2 or backlog:**

- Recently-pulled with server-side persistence (opt-in): only if owner requests cross-session persistence after v2.1 ships.
- "What's new" full list view on admin diagnostics: count badge is sufficient for v2.1.
- AUTH-01 OAuth2 device authorization grant: explicitly deferred per PROJECT.md.
- "New" badge on kiosk search results (P2, not P1).

### Architecture Approach

v2.1 lands cleanly on the existing v2.0 architecture. Migration head is 0011 (`devices` + `pairing_codes`); v2.1 adds a single migration (0012) that creates `invite_redemptions` and adds `profiles.prev_sync_item_count`. Per-profile registries (cache, event-bus, state) keyed by `profile_id` are the existing isolation mechanism; the DEV-02 fix wires the kiosk SSE consumer to actually handle device lifecycle events the server already publishes. The `write_boundary` fix adds `AND profile_id = %s::uuid` to every UPDATE/DELETE on `cube_boundaries` and propagates the parameter through all callers in `admin/cubes.py` — no migration, pure Python change.

**Major components and their v2.1 changes:**

1. `db/queries.py write_boundary()`: Add `profile_id` to WHERE clause; propagate through all callers in `admin/cubes.py`. (Tech debt closure — must be Wave 1.)
2. `invite_redemptions` table + invite endpoints (`POST /api/admin/profiles/{pid}/invite`, `GET /api/invite/{token}`, `POST /api/invite/{token}/redeem`): New. Token as URL path segment, `Referrer-Policy: no-referrer`, single-use enforced by DB insert.
3. `POST /api/kiosk/reset`: New public endpoint (no PIN). Clears browse-binding cookie; no server state mutation.
4. `_swap_inside_tx()` in `sync/profile_sync.py`: Capture `prev_sync_item_count` before UPDATE; add `item_count_delta` to `collection_changed` SSE payload.
5. Kiosk SSE consumer (React `useSSEConnection` hook): Add `device_revoked` / `device_reassigned` handlers; exponential backoff reconnect; 403-device-revoked as terminal state.
6. `OfflineBanner` component + Zustand connectivity slice: SSE state drives all offline UI; `navigator.onLine` is secondary cosmetic signal only.
7. `<QRCode>` in kiosk pairing page: Frontend-only; QR encodes `http[s]://{GRUVAX_EXTERNAL_BASE_URL}/admin/pair?code={current_4digit}` via the existing 4-digit code + same TTL + same bind endpoint.
8. `useRecentSearches` + `sessionStorage`: Frontend hook; cleared by `POST /api/kiosk/reset` action and idle-timeout handler.

### Critical Pitfalls

The research identified 20 v2.1-specific pitfalls (Pitfall 24–43). The nine classified Critical each require a named owner in their executing phase:

1. **Invite token referrer and log leakage (P24):** Use URL path segment (`/invite/{token}`), not `?token=` query param. Set `Referrer-Policy: no-referrer` on accept page. Suppress Uvicorn access log for `/invite/` routes. TTL maximum 30 minutes.
2. **Invite token replay within TTL (P25):** `invite_redemptions` table with `token_sig PRIMARY KEY`; `FOR UPDATE` on lookup + mark in one transaction. Second POST returns 410 Gone. Integration test required.
3. **Owner reads back member's PAT (P26):** `ProfileResponse` exposes only `has_token: bool`. Never `app_token_encrypted` or any derivative. Test: GET profile response JSON contains no field with "token" or "encrypted" in key or value.
4. **Wrong/over-scoped PAT silently accepted (P27):** Validate PAT against discogsography before storing. Return 422 on 401/403 or username mismatch. Return 503 if discogsography unreachable — never store an unvalidated token.
5. **QR encodes a reusable credential (P28):** QR encodes 4-digit code URL (not the code itself as raw value); auto-rotate every 60 seconds; rate-limit bind endpoint; both QR and PIN paths share `complete_pairing()`.
6. **QR and PIN paths diverge in security (P29):** Single shared `complete_pairing()` function for both paths. Both emit identical audit log entries. Integration test matrix covers both paths.
7. **Query text in structlog (P30):** structlog pipeline processor intercepts any record with `query` key and replaces value with `"<redacted>"`. CI asserts: after 5 searches, `docker logs gruvax-api | grep <search_term>` returns zero hits.
8. **Session history in localStorage (P31):** `sessionStorage` only. Zustand `persist` middleware must use `partialize` to exclude `recentSearches`.
9. **Reset-kiosk as admin bypass (P32):** Reset is purely client-side — no API calls. Hidden during active admin session.

## Implications for Roadmap

The dependency chain from architecture research enforces a clear 5-phase grouping.

### Phase 1: Tech-Debt Closure

**Rationale:** `write_boundary` without `profile_id` is a silent data-integrity hazard on multi-profile deployments. Any boundary-editing UI that lands before this fix can corrupt the wrong profile's boundaries. The kiosk's missing `device_revoked`/`device_reassigned` SSE handlers block the offline UX terminal-revoke case. Both are pure code changes with no migration — lowest-risk, highest-leverage work in the milestone.

**Delivers:** Safe multi-profile boundary writes; kiosk SSE consumer handles device lifecycle events; `boundary_changed` fan-out verified to use per-profile bus.

**Addresses:** DEV-02 (SSE fan-out + device lifecycle handlers); write_boundary profile_id scoping.

**Avoids:** Pitfall 33 (cross-profile boundary corruption); Pitfall 34 (SSE fan-out to wrong profile); unblocks Pitfall 35 terminal-revoke handling.

**Research flag:** Standard patterns; no additional research needed. Grep-verify all `write_boundary` call sites before merging.

### Phase 2: Schema Migration (0012)

**Rationale:** AUTH-02 and API-04 both require schema changes. Combining into migration 0012 minimizes round-trips. Alembic round-trip invariant must pass in CI before any feature code lands.

**Delivers:** Migration 0012 — `invite_redemptions` table + `profiles.prev_sync_item_count` column. No application features yet.

**Addresses:** Pre-condition for Phase 3.

**Research flag:** Standard Alembic async migration pattern; no additional research needed.

### Phase 3: Auth/Invite + Collection Diff

**Rationale:** Both features depend only on migration 0012 and existing shipped infrastructure. Can be parallelized. AUTH-02 is the highest P1 feature — household member onboarding is the core new capability.

**Delivers:**
- AUTH-02: full invite flow with security posture (path-segment token, referrer policy, single-use, PAT validation, has_token schema, 409 guard on re-invite).
- API-04: `prev_sync_item_count` populated by sync; `item_count_delta` in `collection_changed` SSE; count badge in admin diagnostics card.

**Addresses:** AUTH-02, API-04.

**Avoids:** Pitfalls 24–27 (AUTH-02 security cluster); Pitfall 38 (invite overwrites existing PAT); Pitfall 41 (diff count inflation — use `discogs_added_at`).

**Research flag:** AUTH-02 requires verification against the 7-item "Looks Done But Isn't" checklist in PITFALLS.md before phase closes. Discogsography test double must be in place before CI can run PAT-validation tests without network access.

### Phase 4: Privacy + SRCH-09 + QR Pairing + Offline UX

**Rationale:** DEV-04 is frontend-only — can be developed in parallel with any Phase 4 work. PRIV-01..04 and SRCH-09 share `sessionStorage` semantics and must ship together. OFF-01..04 needs Phase 1's DEV-02 SSE handler fix in place for the terminal-revoke case.

**Delivers:**
- DEV-04: `<QRCode>` on kiosk pairing screen; `/admin/pair?code=XXXX` pre-fill; `GRUVAX_EXTERNAL_BASE_URL` env var for QR URL construction.
- PRIV-01..04 + SRCH-09: structlog `query` field redaction processor; `POST /api/kiosk/reset` endpoint (client-side-only); `sessionStorage`-backed recently-pulled list; "Reset kiosk" button; idle-timeout extended to clear sessionStorage.
- OFF-01..04: `useSSEConnection` hook with exponential backoff; Zustand `connectionState` slice; `OfflineBanner` component; TanStack Query invalidation on `server_hello`; SSE initial `retry:` with per-client jitter; `useBackendOnline` hook against `/healthz`.

**Addresses:** DEV-04, PRIV-01..04, SRCH-09, OFF-01..04.

**Avoids:** Pitfall 28 (QR nonce vs credential); Pitfall 29 (shared `complete_pairing()`); Pitfall 30 (structlog processor); Pitfalls 31/40 (sessionStorage, Zustand persist partialize); Pitfall 32 (reset-kiosk client-side only); Pitfall 35 (SSE-state as primary offline signal); Pitfall 36 (reconnect storm — per-client `retry:` jitter); Pitfall 43 (QR physical size — hardware-in-the-loop test required).

**Research flag:** DEV-04 requires a pre-implementation Key Decision on QR HTTP vs HTTPS (Pitfall 39). Recommend Option A (HTTP + 60-second nonce rotation + single-use, documented). OFF-01..04: use `networkMode: 'always'` not `'offlineFirst'` (PITFALLS reasoning wins over STACK recommendation — prevents paused-query thundering herd on reconnect; see Pitfall 36).

### Phase 5: Shelf Fill-Overview + Milestone Closure

**Rationale:** Depends on Phase 1 (`write_boundary` fix ensures fill data is profile-scoped correctly). Lowest complexity item — frontend-only, data already in `GET /api/admin/cubes`. Serves as milestone polish close-out.

**Delivers:** `fill_level` and `is_empty` on cubes API response; `LocatorHeader` mini 4×4 Kallax renders fill shading; GSAP spring animation on fill bars at mount; fill indicator in boundary editor.

**Addresses:** ex-999.1 shelf fill-overview.

**Research flag:** Standard frontend patterns; reuses existing TanStack Query invalidation and design tokens. No additional research needed.

### Phase Ordering Rationale

- Tech debt first: write_boundary corruption is silent; DEV-02 gap blocks offline terminal-revoke case.
- Schema migration second: separates schema from code; both AUTH-02 and API-04 depend on it.
- Auth + Diff in parallel (Phase 3): both depend only on migration 0012 and shipped infrastructure.
- Privacy/SRCH-09/Offline in Phase 4: PRIV-01 and SRCH-09 share sessionStorage semantics; offline UX needs Phase 1's SSE fixes.
- Shelf fill last: purely additive polish, no blockers beyond Phase 1.

### Open Questions — Must Be Decided Before Implementation

1. **QR HTTP vs HTTPS (Pitfall 39):** Option A (HTTP + 60-second nonce rotation + single-use, documented), B (HTTP + server-side confirmation step), or C (HTTPS with self-signed CA). Recommend Option A as proportionate to home-LAN threat model. Must decide before DEV-04 implementation starts.
2. **Invite-redeem TLS posture:** The redeem POST sends the member's PAT in plaintext on HTTP. Document in runbook; flag for TLS if deployment ever extends beyond home LAN.
3. **`arrived_at` vs per-row timestamp naming:** ARCHITECTURE.md uses `profiles.prev_sync_item_count` (scalar, not per-row). This is the accepted approach. Any new timestamp column name on `profile_collection` (if added for future per-record diff) must be settled before the migration is written.
4. **Discogsography test double in CI:** PAT validation in invite-redeem calls discogsography's collection API. A VCR cassette or mock HTTP client must be in place before AUTH-02 tests can run in CI without network access.
5. **`networkMode` configuration:** Use `'always'` (not `'offlineFirst'`). PITFALLS reasoning is correct — prevents thundering-herd reconnect storm (Pitfall 36). Read Pitfall 36 before configuring TanStack Query.

### Research Flags

Phases needing careful implementation review (not additional external research):

- **Phase 3 (AUTH-02):** 7-item "Looks Done But Isn't" checklist from PITFALLS.md must pass before phase closes.
- **Phase 4 (DEV-04):** Pre-implementation Key Decision on HTTP/HTTPS (Pitfall 39). Hardware-in-the-loop QR scan test on actual 7" display before shipping.
- **Phase 4 (OFF-01..04):** `networkMode: 'always'` configuration; SSE jitter via `retry:` field.

Phases with standard patterns (skip additional research):

- **Phase 1 (Tech Debt):** Pure code changes; grep-verify call sites.
- **Phase 2 (Schema):** Standard Alembic async migration.
- **Phase 5 (Shelf Fill):** Frontend-only; reuses existing data and tokens.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All additions verified against PyPI, npm, and Context7 docs. One researcher disagreement on `networkMode` resolved by PITFALLS reasoning. |
| Features | HIGH | Grounded in established privacy, invite-flow, and kiosk UX patterns. API-04 diff has no direct prior art but implementation pattern is unambiguous. |
| Architecture | HIGH | Verified against live source files (`src/gruvax/`, `migrations/`) as of 2026-05-30. Integration points are concrete and low-risk. |
| Pitfalls | HIGH | Security pitfalls (24–32) anchored to MDN, OWASP, PortSwigger, and HackerOne reports. SSE/offline pitfalls anchored to TanStack Query docs and EventSource spec. |

**Overall confidence:** HIGH

### Gaps to Address

- **`networkMode` configuration disagreement:** STACK.md recommends `offlineFirst`; PITFALLS.md recommends `always`. Resolution: use `networkMode: 'always'`. The PITFALLS reasoning (prevents paused-query thundering herd on SSE reconnect) is the correct call for this SSE-driven app. See Pitfall 36.
- **Discogsography test double:** PAT validation requires a live discogsography call. Test strategy (VCR cassette vs mock HTTP client) must be decided at Phase 3 planning time.
- **ARCHITECTURE vs STACK minor divergence on invite storage:** STACK.md describes a fuller `invite_tokens` table; ARCHITECTURE.md uses a leaner `invite_redemptions` table (token_sig + consumed_at, relying on `itsdangerous` TTL for expiry). **Use the ARCHITECTURE.md design** — avoids a cleanup job and expiry column.

## Sources

### Primary (HIGH confidence)

- `src/gruvax/sync/profile_sync.py` — staging-swap implementation (verified live, 2026-05-30)
- `src/gruvax/api/events.py` — per-profile SSE channel (verified live, 2026-05-30)
- `src/gruvax/db/queries.py` — `write_boundary()` confirmed missing `profile_id` in WHERE (verified live, 2026-05-30)
- `migrations/versions/0011_devices_and_pairing_codes.py` — current schema head (verified live, 2026-05-30)
- [react-qr-code on npm](https://www.npmjs.com/package/react-qr-code) — version 2.0.21, last published 2026-04-29
- [itsdangerous Context7 docs](/pallets/itsdangerous) — `URLSafeTimedSerializer`, `max_age`, `SignatureExpired`, `BadData`
- [TanStack Query v5 Network Mode docs](https://tanstack.com/query/v5/docs/react/guides/network-mode) — `networkMode` modes confirmed
- [MDN: `navigator.onLine`](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/onLine) — unreliability for LAN scenarios documented
- [MDN: Referer header privacy and security concerns](https://developer.mozilla.org/en-US/docs/Web/Privacy/Guides/Referer_header:_privacy_and_security_concerns) — token leakage via referrer; `Referrer-Policy: no-referrer`
- [Cryptography.io Fernet docs](https://cryptography.io/en/latest/fernet/) — TTL parameter on `decrypt()`

### Secondary (MEDIUM confidence)

- [Cendyne.dev: Dual-Device Authorization with QR Codes (2025-02-17)](https://cendyne.dev/posts/2025-02-17-qr-code-login.html) — QR encodes opaque session reference not credential
- [natlas invite token replay issue (GitHub)](https://github.com/natlas/natlas/issues/139) — real-world invite token replay; single-use pattern required
- [HackerOne Semrush report #342693](https://hackerone.com/reports/342693) — password-reset token leak via referrer; mirrors invite-token risk
- [TanStack Query optimistic update race discussion #7932](https://github.com/TanStack/query/discussions/7932) — reconnect racing optimistic updates
- [Porteus Kiosk](https://porteus-kiosk.org/) — session-only, RAM-only, never-persist-history kiosk reference OS
- [Clockify Help — Kiosk Clock-in Authentication](https://clockify.me/help/track-time-and-expenses/pin) — QR and PIN as parallel paths to same endpoint
- [Wavetec — Best Practices for Kiosk Installations in Low-Connectivity Zones](https://www.wavetec.com/blog/best-practices-of-kiosk-installations-in-low-connectivity-zones/) — degraded mode, auto-sync

---
*Research completed: 2026-05-30*
*Ready for roadmap: yes*

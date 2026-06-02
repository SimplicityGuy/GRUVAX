# Requirements: GRUVAX — v2.1 Resilience + Privacy + UX polish

**Defined:** 2026-05-30
**Core Value:** Type artist / title / label / catalog# → see the right cube (and a sub-cube position estimate) on the touchscreen within ~200 ms. Everything else is decoration.

> Milestone scope was locked as "the v2.0 parked candidate scope, as-is" + the shelf-fill UX item promoted from backlog 999.1. Requirements below reuse the IDs assigned in the v2.0 archive where they already existed. Phase numbering **continues** from v2.0 (v2.1 starts at Phase 6).

## v2.1 Requirements

### Member Onboarding (Auth)

- [x] **AUTH-02**: Owner can issue a one-time, time-limited invite link for a profile; the member opens it and pastes **their own** discogsography PAT into a GRUVAX-served form. The token is stored Fernet-encrypted on that profile; the owner never sees the raw token (responses expose only `has_token: bool`). Invite is single-use (`consumed_at`) and TTL-bounded; an expired/used/invalid token shows a clear redeem error. No GRUVAX member login account is created — the flow is purely "deposit your PAT into a profile slot."

### Devices & Pairing

- [x] **DEV-04**: The kiosk pairing screen presents a **QR code alongside** the existing 4-digit PIN. The admin can scan the QR on a phone (opens the bind page prefilled with the current code) **or** type the code — both paths call the same bind endpoint. The QR re-renders when the pairing code auto-rerolls. The QR encodes a bind **URL carrying an opaque short-TTL code**, never a credential.
- [x] **DEV-05**: The kiosk reflects device **switch / revoke live via SSE** — a re-bind or revoke takes effect without a manual reload (closes the v2.0 DEV-02 SSE-immediacy tech debt). On revoke (403 terminal), the kiosk reverts to the profile-picker / pairing screen.

### Sync & Collection

- [x] **API-04**: After a sync (nightly or manual), the kiosk and admin surface a per-profile **"N new records since last sync"** indicator. The diff **count** is computed in the existing staging-swap sync and delivered on the `collection_changed` SSE payload. (Set-level "which records" diff is out of scope — count only.)

### Search

- [x] **SRCH-09**: The kiosk keeps a **session-only recently-pulled list** of records recently searched/located, cleared on session end / idle timeout / kiosk reset. No server-side persistence.

### Offline & Resilience

- [x] **OFF-01**: When the kiosk loses its connection to the GRUVAX backend, it shows a clear **offline banner** (SSE connection-state is the authoritative signal, not `navigator.onLine`).
- [x] **OFF-02**: While offline the kiosk enters **degraded mode** — search input disabled, but the last locate result / cube highlight stays visible (never serve stale boundaries as fresh).
- [x] **OFF-03**: The kiosk **auto-reconnects with backoff + jitter** (SSE reconnect + `/healthz` probe), without a reconnect storm.
- [x] **OFF-04**: On successful reconnect the banner clears, search re-enables, and stale data is refreshed (TanStack Query invalidation on `server_hello`).

### Privacy

- [x] **PRIV-01**: Search history is **session-only** (`sessionStorage` / in-memory) and never persists across a kiosk restart; the Zustand `persist` slice explicitly excludes the history.
- [x] **PRIV-02**: The server **never persists or logs raw query text** — structlog redacts the `q` field and the uvicorn access-log query string is suppressed. Enforced by a CI test asserting no plaintext query appears in logs. (De-facto met since v1.0 Phase 8; formalized + test-locked here.)
- [x] **PRIV-03**: Record statistics are **aggregate-only** (per-`release_id` counters; no per-query `search_log` table). (De-facto met since v1.0 Phase 8; formalized here.)
- [x] **PRIV-04**: A **no-PIN "Reset kiosk"** affordance clears the local session **client-side only** (no API call, no device unbind), and is hidden during an active admin session.

### UX Polish

- [ ] **UX-01**: The admin ShelfBinList `LocatorHeader` mini 4×4 Kallax shows **per-cube fill/occupancy** at a glance (`is_empty` / `fill_level` from `GET /api/admin/cubes`) instead of uniform dim tiles, honoring the CUBE-05 empty-cube desaturated state. (Promoted from backlog 999.1.)

### Data Integrity & Tech-Debt Closure

- [x] **DATA-01**: `write_boundary` is **scoped by `profile_id`** in its WHERE clause (cross-profile write isolation), and `boundary_changed` SSE fan-out is **per-profile** (not default-profile-only). **Load-bearing — must land before any multi-profile boundary-editing UI.**

## Out of Scope

| Feature | Reason |
|---------|--------|
| AUTH-01 — OAuth2 device-authorization grant (no PAT crosses the household) | Larger auth re-architecture; deferred to v2.2. AUTH-02 invite-token is the v2.1 step. |
| LED "party" / "sound-reactive" modes (backlog 999.2) | Gated on the future real-LED hardware milestone to be observable. |
| Real LED hardware end-to-end (ESP32 + WS2812B firmware) | Independent hardware milestone; v2.1 stays software-only. |
| Offline-first PWA / service-worker search cache | Anti-feature for this kiosk — stale boundaries are worse than no results. Offline is detect-and-reconnect, not operate-without-server. |
| Set-level collection diff ("which records changed") | v2.1 surfaces the **count** only; per-record diff adds complexity without proportional value. |
| GRUVAX member login accounts | Invite flow is PAT-deposit only; no second auth system beyond the owner PIN. |
| Server-side persisted search history | Conflicts with PRIV-01 by default; would be an explicit opt-in differentiator, not v2.1. |

## Open Decisions (resolve at discuss/plan time, before the owning phase)

| Decision | Recommendation | Owning Phase |
|----------|----------------|-------------|
| QR pairing over HTTP vs HTTPS on the home LAN | HTTP + 60s rotating single-use nonce (proportionate to home threat model); document in Key Decisions | Phase 8 (DEV-04) |
| Invite-redeem posts the member PAT over plaintext HTTP on LAN | Document as a runbook note; TLS optional for home LAN | Phase 7 (AUTH-02) |
| New-record cache column name: `arrived_at` vs `first_seen_at` (avoid clash with Discogs `date_added`) | `first_seen_at` (GRUVAX-cache arrival, distinct from Discogs date) | Phase 7 (API-04) |
| TanStack Query `networkMode` for reconnect | `'always'` (prevents reconnect-triggered refetch storm; PITFALLS overrides STACK here) | Phase 9 (OFF-03) |
| Discogsography contract: token-validation call during invite redeem + diff support in CI fixture | Confirm fake-discogsography fixture supports a `limit=1` validation call | Phase 7 (AUTH-02, API-04) |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | Phase 6 | Complete |
| DEV-05 | Phase 6 | Complete |
| AUTH-02 | Phase 7 | Complete |
| API-04 | Phase 7 | Complete |
| DEV-04 | Phase 8 | Complete |
| PRIV-01 | Phase 8 | Complete |
| PRIV-02 | Phase 8 | Complete |
| PRIV-03 | Phase 8 | Complete |
| PRIV-04 | Phase 8 | Complete |
| SRCH-09 | Phase 8 | Complete |
| OFF-01 | Phase 9 | Complete |
| OFF-02 | Phase 9 | Complete |
| OFF-03 | Phase 9 | Complete |
| OFF-04 | Phase 9 | Complete |
| UX-01 | Phase 10 | Pending |

**Coverage:**
- v2.1 requirements: 15 total
- Mapped to phases: 15 / 15 (100%) ✓
- Unmapped: 0

---
*Requirements defined: 2026-05-30*
*Last updated: 2026-05-30 — traceability table filled after roadmap creation*

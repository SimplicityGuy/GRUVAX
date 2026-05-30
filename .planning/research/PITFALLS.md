# Pitfalls Research — GRUVAX v2.1 (Resilience + Privacy + UX Polish)

**Domain:** Adding invite-token member onboarding, QR-code kiosk pairing, offline/reconnect UX, query-privacy enforcement, and v2.0 tech-debt closure to a shipped Python/FastAPI + React household vinyl-locator kiosk.
**Researched:** 2026-05-30
**Confidence:** HIGH on security and privacy pitfalls (anchored to current MDN/OWASP guidance and verified patterns). HIGH on SSE/offline pitfalls (anchored to TanStack Query network-mode docs and EventSource spec). MEDIUM on QR pairing MITM (home-LAN threat model reduces many enterprise risks but does not eliminate them).

This document covers **only v2.1-specific pitfalls**. The v1.0 pitfall catalog (catalog-number sort, retained MQTT state, squeekboard, etc.) remains the authoritative reference for v1-era concerns. Every prevention strategy here references a concrete GRUVAX surface.

**Severity legend:**
- **Critical** — silently corrupts data, leaks a secret, or makes a security promise false.
- **Major** — multi-hour fix or broken named feature; no data corruption or secret leak.
- **Minor** — annoying but quickly fixable; no security or integrity impact.

---

## Critical Pitfalls

### Pitfall 24: Invite token leaks via Referrer header or Uvicorn access log

**What goes wrong:**
The invite URL is `https://gruvax.local/invite/accept?token=<fernet_ciphertext>`. The member opens the link on their phone, which may have a browser extension that pings an analytics service on navigation, or may load a resource from an external domain (a font, a favicon, any `<img src>` or `<link>` in the accept page). The browser sends `Referer: https://gruvax.local/invite/accept?token=<ciphertext>` to that external domain. The token is now in that third party's access log. Simultaneously, Uvicorn's default access log records the full request path including the query string — the token appears in `journalctl` and Docker's `json-file` log in plaintext.

Even though the token is Fernet-encrypted (not a raw PAT), an attacker with that log entry has a valid single-use invite link they can race against the real member.

**Why it happens:**
Invite tokens placed in URL query strings are subject to referrer leakage regardless of encryption. Uvicorn logs the full path by default; any docker logs capture or log-shipper will contain the token. This is a well-documented class of vulnerability with multiple HackerOne reports on password-reset tokens following the same pattern.

**Warning signs:**
- The `GET /invite/accept` endpoint accepts `?token=` as a query parameter.
- Uvicorn's `--access-log` is enabled in the production `CMD`.
- The accept page loads any resource from a domain other than `gruvax.local`.
- `docker logs gruvax-api` shows invite token strings in the path field.

**Prevention:**
- **Use `POST` body or URL path segment, not `?token=` query parameter.** The invite URL is `GET /invite/{token}` (path param), which still shows in Uvicorn's access log, OR a two-step flow: the email/QR-code carries a short opaque code (`/invite/accept#code=XXXX`) and the actual token lives in a POST body the JS submits. The cleanest approach for a LAN app with no external resources: use a path segment (`/invite/{token}`) and suppress the Uvicorn access log on that specific path via a custom `LogFilter` on `uvicorn.access`.
- **Set `Referrer-Policy: no-referrer` on the invite accept page** via a response header from FastAPI. This instructs the browser not to send the `Referer` header for any resource the page loads.
- **Suppress Uvicorn access log entries for `/invite/` routes** in production. Use a structlog-based middleware that logs the invite path as `/invite/<redacted>` and sets `access_log=False` for Uvicorn; the structlog layer logs with the token hash (first 8 chars only) for audit.
- **Short TTL (30 minutes maximum).** Fernet's built-in `ttl` parameter enforces this at decryption time. Even if the token leaks, a 30-minute window is the attack surface.
- **Single-use: mark consumed in DB immediately on first valid decrypt.** The `invite_tokens` table row gets `used_at = now()` in the same transaction that creates the profile's encrypted PAT. Any second attempt returns 410 Gone, even if the TTL has not expired.

**Phase to address:**
AUTH-02 phase (invite-token backend) must own the referrer-policy header, the Uvicorn log filter, the single-use DB write, and the short TTL. The invite acceptance frontend page must not load any external resources.

---

### Pitfall 25: Invite token is not single-use — replay window after member completes onboarding

**What goes wrong:**
The server generates a Fernet token with a 24-hour TTL. The member completes onboarding at T+5 minutes. At T+12 hours, the same token link (still valid by TTL) is forwarded in a group chat. A second household member pastes their own PAT into the same invite form. The invite link is effectively reusable for anyone who has it within the TTL window.

**Why it happens:**
Fernet's TTL only prevents time-expired replays. Without a server-side "was this token already consumed?" check, the token is reusable within the TTL window. This is a standard replay-attack failure mode — the same pattern that bit natlas and multiple HackerOne-disclosed password-reset flows.

**Warning signs:**
- The `invite_tokens` table lacks a `used_at` column.
- The `POST /api/admin/invite/accept` handler decrypts the token and proceeds without checking any server-side state.
- Integration tests do not attempt a second POST with the same token after a successful first POST.

**Prevention:**
- **`invite_tokens` table with `(id, token_hash, profile_id, created_at, expires_at, used_at nullable)`.** The handler: (1) decrypt and TTL-check via Fernet, (2) look up `token_hash` in the table, (3) if `used_at IS NOT NULL`, return 410 Gone, (4) otherwise set `used_at = now()` and proceed — all in one database transaction with `FOR UPDATE` to prevent concurrent double-use.
- **Token hash:** store `sha256(token_bytes)`, not the token itself, so the DB row cannot be used to reconstruct the token.
- **TTL ≤ 30 minutes.** The shorter the TTL, the smaller the replay window even if the single-use check fails.
- **Integration test: POST the same token twice; assert the second returns 410.**

**Phase to address:**
AUTH-02 phase. The `invite_tokens` table is the minimal schema addition; the `FOR UPDATE` transaction is the critical implementation detail.

---

### Pitfall 26: Owner can read back a member's PAT after it is stored

**What goes wrong:**
The invite flow's stated privacy guarantee is: "member pastes their own PAT; owner never sees it." If the `/api/admin/invite/accept` response body echoes the accepted PAT, or if the admin's "profiles" GET endpoint returns the Fernet-encrypted PAT field (even encrypted), the owner can:
(a) copy the ciphertext and decrypt it with GRUVAX's Fernet key (which the owner controls), or
(b) the frontend inadvertently renders the field in a dev-mode React component tree inspector.

**Why it happens:**
FastAPI response models default to returning all fields on a Pydantic model. If `Profile` includes `app_token_encrypted`, it will appear in `GET /api/admin/profiles/{id}` unless explicitly excluded. The owner is the same person who controls the server and holds the Fernet key, so encryption does not protect the PAT *from the owner*.

**Warning signs:**
- The `ProfileResponse` Pydantic model includes `app_token_encrypted`.
- `GET /api/admin/profiles/{id}` returns a field whose name contains "token" or "encrypted."
- The admin profile detail page renders all API response fields.

**Prevention:**
- **`ProfileResponse` schema never includes `app_token_encrypted` or any derivative.** Use a separate `ProfileAdminResponse` for the admin panel that contains only `id`, `display_name`, `discogs_username`, `last_sync_at`, `last_sync_status`, `has_token: bool` (a boolean computed server-side: `app_token_encrypted IS NOT NULL`). The `has_token` field tells the admin "this profile has a connected PAT" without exposing the token or its ciphertext.
- **No endpoint returns the encrypted token.** The only operation on the token after storage is: (a) use it for sync (internal only), (b) overwrite it (via re-invite), (c) clear it (revoke).
- **Add a `has_token` field to the profile response** so the admin UI can show "Connected / Not connected" without needing the token value.
- **Test:** `GET /api/admin/profiles/{id}` response JSON must not contain the string "token" or "encrypted" in any key or value.

**Phase to address:**
AUTH-02 phase. This is a response-schema discipline issue; the Pydantic model is the enforcement point.

---

### Pitfall 27: Member pastes a wrong or over-scoped PAT — silently accepted

**What goes wrong:**
The invite form says "paste your discogsography Personal Access Token." The member:
(a) pastes a classic wide-scope PAT instead of a `collection:read`-scoped one, or
(b) pastes a PAT for a different discogsography user (copy-paste error from another tab),
(c) pastes a plaintext string that is not a PAT at all.

In case (a), GRUVAX stores an over-privileged credential (privacy/security concern). In cases (b) and (c), nightly sync will fail silently with a 401, and the profile appears broken for no obvious reason.

**Why it happens:**
Fernet encryption happens client-side-agnostic: the server receives whatever the member typed, encrypts it, and stores it. Without a validation round-trip to discogsography before storing, the token is "accepted" regardless of its validity or scope.

**Warning signs:**
- The `POST /api/admin/invite/accept` handler stores the PAT without a test API call to discogsography.
- The invite form has no scope guidance ("use `collection:read` scope only").
- The first sync fails 24 hours after onboarding with a 401 error the member doesn't understand.

**Prevention:**
- **Validate the PAT immediately before storing.** The accept handler makes one `GET /api/user/collection?limit=1` request to the discogsography API with the supplied PAT. If it returns 200, the PAT is valid and the user identity is confirmed. If it returns 401/403, return a 422 to the invite form: "Token is invalid or lacks collection:read access." If it returns wrong user (the profile `discogs_username` from the invite payload does not match the API response's username field), return a 422: "This token belongs to a different Discogs account."
- **The invite payload includes the expected `discogs_username`** (owner fills this in when generating the invite). The accept handler compares the identity the PAT authenticates as against the expected username.
- **Invite form copy:** "Create a Personal Access Token in discogsography with `collection:read` scope only. Do not use a wide-scope token."
- **Scope check:** discogsography's `GET /api/user/collection` will return 403 if the PAT lacks `collection:read`. This doubles as a scope validator.
- **If discogsography is temporarily unreachable** (during an invite accept attempt): return 503 "Cannot validate token right now — try again in a moment." Do not store an unvalidated token.

**Phase to address:**
AUTH-02 phase. The validation call is a mandatory step in the accept handler, not an optional audit.

---

### Pitfall 28: QR code encodes a reusable credential instead of an opaque bind URL

**What goes wrong:**
The kiosk displays a QR code for pairing. If the QR encodes the existing 4-digit PIN (or any persistent credential), anyone with a camera who walks past the kiosk can photograph it and use that credential later — on the LAN, on a different device, or shared in a group chat. The QR code becomes a permanently-visible credential display.

**Why it happens:**
It is tempting to encode "whatever the device needs to authenticate" directly into the QR code for simplicity. The error is treating the QR as a secure channel when it is an optical broadcast to anyone with a camera.

**Warning signs:**
- The QR code encodes the 4-digit pairing code, the PIN hash, or any reusable credential.
- The QR code does not expire.
- The same QR code is valid indefinitely or until manually regenerated.

**Prevention:**
- **The QR encodes only an opaque, time-limited, single-use bind URL:** `http://gruvax.local:PORT/api/devices/pair/qr/{nonce}` where `nonce` is a 128-bit cryptographically random value stored in the `pairing_codes` table with a 5-minute TTL.
- **The nonce is NOT the 4-digit code** — it is a separate, longer secret generated purely for QR use. The admin's phone opens the URL (or the SPA reads it), which completes the bind server-side. The 4-digit code path remains separate and valid simultaneously.
- **The QR auto-rotates every 60 seconds** by generating a new nonce. The old nonce is invalidated server-side. This limits the window in which a photo attack is viable.
- **Single-use:** the `pairing_codes` row is marked `used_at = now()` on first successful bind, even within the TTL.
- **The QR bind endpoint is rate-limited** (5 attempts per 5 minutes per IP) to prevent brute-force nonce guessing.

**Phase to address:**
DEV-04 phase. The existing 4-digit code flow (v2.0) must NOT be changed — it remains a parallel path. DEV-04 adds a separate nonce-based QR path on top of it.

---

### Pitfall 29: QR pairing and 4-digit code both accepted simultaneously — two unguarded paths

**What goes wrong:**
v2.0 ships the 4-digit code flow. v2.1 adds QR. If both paths remain active indefinitely and the QR nonce path is less strictly rate-limited than the 4-digit path, the QR path becomes the easier attack surface. Alternatively, the QR path skips some validation that the PIN path enforces (e.g., the QR path does not require admin confirmation).

**Why it happens:**
The QR path is implemented as an additive feature on top of the existing flow. Under time pressure, parity checks between the two paths are skipped.

**Warning signs:**
- The QR nonce bind endpoint (`/api/devices/pair/qr/{nonce}`) has no rate limit.
- The QR path does not emit the same device-created audit log entry that the 4-digit path emits.
- The QR path does not enforce the same `pairing_codes` TTL logic as the 4-digit path.
- Integration tests exercise only one path.

**Prevention:**
- **Both paths share the same `pairing_codes` table and TTL logic.** The QR nonce is just another column: `(code_4digit, qr_nonce, profile_id, created_at, expires_at, used_at)`. The bind logic is a single `complete_pairing(pairing_code_id)` function called by both handlers.
- **Both paths emit identical audit log entries** to the `change_log` table: `action: device_paired, device_id: ..., method: qr|pin`.
- **Both paths have equivalent rate limits.** If the 4-digit path is 5 attempts/5 minutes per IP, the QR nonce path is also rate-limited (nonce guessing is harder, but the rate limit is the safety net for path parity).
- **Integration test matrix:** test both paths for: happy path, expired TTL, second use of same token, rate-limit breach.

**Phase to address:**
DEV-04 phase. The shared `complete_pairing` function is the architectural discipline that prevents divergence.

---

### Pitfall 30: Query text leaks into structlog output despite "no server-side persistence" promise

**What goes wrong:**
PRIV-01 promises no server-side query-text storage. But the search handler logs `log.info("search", query=q, profile_id=...)` at INFO level. The structlog JSON lands in Docker's `json-file` log, which is preserved across container restarts (Docker log rotation keeps the last 3 files per the v1 ops pitfall). The effective retention is 3 × 10 MB = up to 30 MB of logs containing real user queries. The "no persistence" promise is false.

**Why it happens:**
The existing v1.0 PITFALLS.md already calls out "search query redaction" as a checklist item (Pitfall v1 Technical Debt: "Search query body logged in plaintext"). In v2.1, the PRIV-01..04 requirements make this a first-class named requirement, which means the existing v1 pattern needs to be audited and enforced, not just mentioned. Under time pressure the structlog field is added for debugging and never removed.

**Warning signs:**
- `docker logs gruvax-api | grep '"query"'` returns matches for user search strings.
- The structlog configuration does not include a processor that redacts the `query` field.
- Uvicorn's `--access-log` is enabled, logging `GET /api/search?q=radiohead`.
- The SSE event payload for `search_completed` includes the query string (which would persist it in any SSE connection log).

**Prevention:**
- **The structlog pipeline includes a `redact_fields` processor** that replaces `query` with `"<redacted>"` for all log records from the search handler. Implement as a structlog processor: if `event_dict.get("query")` is set, replace with `"<redacted>"`. Register at pipeline construction, not per-callsite.
- **The search handler logs only counts and latency:** `log.info("search", query="<redacted>", result_count=N, profile_id=..., latency_ms=X)`. Never the query text.
- **Uvicorn access log is disabled in production** (already a v1 ops pattern; re-verify in v2.1 CI).
- **SSE events for search completion carry only `result_count` and a `request_id`**, never the query string.
- **`GET /api/search` uses query parameters (`?q=radiohead`)** not path segments, so the Uvicorn path log shows `/api/search?q=<value>`. The Uvicorn log filter for `/api/search` must redact the `q` parameter from the logged path, OR Uvicorn access log must be disabled and all audit logging goes through structlog with redaction.
- **Audit:** `grep -r '"query"' src/` and `grep -r 'log.*query' src/` — any callsite that could emit the query string must go through the redactor.

**Phase to address:**
PRIV-01 phase. The structlog processor is the enforcement mechanism. CI must include a test: after a search, `docker logs gruvax-api` must not contain the search string.

---

### Pitfall 31: Session search history persists in localStorage across "no-PIN reset kiosk" and across Chromium sessions

**What goes wrong:**
PRIV-02 requires session-only search history (visible to the current user while they are using the kiosk; gone when they leave). PRIV-04 requires a no-PIN "reset kiosk" button that clears this. If the history is stored in `localStorage` (persistent across Chromium sessions and across kiosk reboots), then:
(a) A visitor's searches are visible to the next visitor who opens the browser.
(b) The kiosk reboot that follows a Compose redeploy does NOT clear `localStorage`, so old history persists.
(c) The Zustand `persist` middleware (used legitimately for wizard `pendingChangeSet`) will also persist the history store if not explicitly excluded.

**Why it happens:**
React/Zustand developers reach for `localStorage` by default for "persistence." The distinction between "persist across sessions" (wizard draft — correct) and "session-only" (search history — must NOT persist) requires explicit per-store configuration. The Zustand `persist` middleware applies to the whole store unless partitioned.

**Warning signs:**
- The Zustand store containing `recentSearches` uses the `persist` middleware.
- Opening Chromium on the kiosk, searching, closing Chromium, reopening Chromium shows the search history.
- The "reset kiosk" action only clears React state (in-memory), not `localStorage`.

**Prevention:**
- **Search history lives in `sessionStorage`, not `localStorage`.** `sessionStorage` is cleared when the browser session ends (tab close or kiosk reboot via the `systemd` unit that kills and restarts Chromium). Zustand's `persist` middleware supports `storage: createSessionStorageWrapper()`.
- **Alternatively, store history only in React component state (not even sessionStorage):** on a kiosk, the browser is always the same process; in-memory state lasts for the kiosk "session" (until Chromium restarts). This is simpler and makes the "no persistence" promise trivially true.
- **The "reset kiosk" (PRIV-04) action calls `sessionStorage.clear()` AND resets React state.** If using in-memory-only, just reset React state.
- **Zustand `persist` middleware must NOT include the `recentSearches` slice.** Explicitly exclude it from the partitioned persist config: `partialize: (state) => ({ pendingChangeSet: state.pendingChangeSet })` — only the wizard draft is persisted.
- **Test:** open kiosk, search for "radiohead", hard-reload Chromium (simulating a reboot), verify the history is empty.

**Phase to address:**
PRIV-02 and PRIV-04 phases. The storage medium choice (sessionStorage vs in-memory) is the single most important decision. Zustand persist partitioning is the guard.

---

### Pitfall 32: "No-PIN reset kiosk" becomes an admin-session bypass

**What goes wrong:**
PRIV-04 adds a "reset kiosk" button visible without a PIN. If this button is accessible on the same page as an active admin session, or if its click handler calls any state-mutating API (not just local state clearing), it becomes an unauthenticated path to modify server state. Specifically: if "reset kiosk" also calls `POST /api/search/history/clear` (a server-side endpoint), that endpoint must not be callable without authentication — but it appears related to the "no PIN" flow.

A more subtle attack: if "reset kiosk" navigates to a URL that triggers an admin action as a side effect (e.g., `GET /api/admin/reset` which was intended for internal use only), anyone can trigger it.

**Why it happens:**
The distinction between "clear local kiosk state" (no auth needed) and "clear server state" (admin auth needed) blurs during implementation. The reset button is designed to be accessible without PIN, so developers avoid authentication on everything it touches — including endpoints that should require it.

**Warning signs:**
- The "reset kiosk" click handler calls any `/api/admin/*` endpoint.
- `POST /api/search/history/clear` does not require an admin session cookie.
- The reset button is visible when an admin session is active — a visitor could use it to terminate the owner's admin session.

**Prevention:**
- **"Reset kiosk" is purely client-side.** It clears `sessionStorage`, resets React/Zustand in-memory state, and navigates to `/` (the search page). It does NOT call any server endpoint.
- **PRIV-01 (no server-side query-text storage) means there is nothing server-side to clear.** The reset button's only job is to clear the client-side session history. If there is no server-side history, the reset is trivially safe.
- **If a "clear stats" or similar server-side action is desired** as part of reset: gate it behind the existing admin PIN. The "no-PIN" requirement applies only to clearing local kiosk state, not server state.
- **The reset button does NOT appear during an active admin session.** Hide it when `isAdminSession === true` in Zustand. This prevents a visitor from disrupting the owner's active boundary editing session.
- **Test (negative):** clicking "reset kiosk" with no admin session active must not result in any API call. Verify via browser network tab or test mock.

**Phase to address:**
PRIV-04 phase. The "client-side only" constraint is the security invariant. Any deviation (even a logging call to the server) must require admin auth.

---

## Major Pitfalls

### Pitfall 33: `write_boundary` WHERE clause missing `profile_id` — cross-profile boundary corruption

**What goes wrong:**
The v2.0 tech-debt item `write_boundary` profile scoping is the most dangerous deferred debt item. If the `UPDATE cube_boundaries SET ... WHERE unit=? AND row=? AND col=?` query does not include `AND profile_id=?`, then an admin editing profile A's boundaries can overwrite profile B's boundaries for the same physical cube position. With two household members each using a 4×4 Kallax unit, this is the "cross-profile write" failure mode the v2.0 architecture was designed to prevent.

**Why it happens:**
The v2.0 audit flagged this as `tech_debt` (not a blocker). The WHERE clause is easy to add — and equally easy to forget under time pressure. SQLAlchemy's `.where()` chaining makes it syntactically simple to add `profile_id` but the code compiles and runs correctly without it (the query just operates on all profiles' matching rows).

**Warning signs:**
- The `write_boundary` handler extracts `profile_id` from the session/cookie but does not pass it to the query.
- The `cube_boundaries` table has `profile_id` NOT NULL but no Postgres Row-Level Security policy enforcing it from within the DB.
- Integration tests only create one profile; the cross-profile write is never exercised.

**Prevention:**
- **Add `AND profile_id = :profile_id` to every `UPDATE cube_boundaries` and `DELETE FROM cube_boundaries` statement.** This is the v2.0 tech-debt closure. SQLAlchemy 2.0 async: `.where(CubeBoundary.profile_id == profile_id)` chained after the existing coordinate filter.
- **Add a Postgres RLS policy** as a defense-in-depth layer: `CREATE POLICY cube_boundaries_profile_isolation ON cube_boundaries USING (profile_id = current_setting('app.profile_id')::uuid)`. Set `current_setting` in each transaction's preamble. This makes the WHERE clause omission a Postgres-level error, not a silent data corruption.
- **Integration test: create two profiles, write boundaries for profile A, attempt write via profile B's session for the same cube coordinates, assert profile A's boundaries are unchanged.**
- **Code review checklist:** every DB mutation for boundary/segment/settings tables must include `profile_id` in the WHERE or VALUES. Add this to the project's PR template.

**Phase to address:**
Tech-debt closure phase (or the first phase that touches boundary writes). This must be resolved before any multi-profile boundary-editing UI is exposed in v2.1.

---

### Pitfall 34: SSE `collection_changed` fan-out sends all profiles' events to the wrong kiosk

**What goes wrong:**
DEV-02 (tech debt): the SSE `boundary_changed` / `collection_changed` event bus currently fans out to all connected SSE clients, not just those bound to the affected profile. A kiosk displaying profile A receives and acts on a `collection_changed` event triggered by profile B's nightly sync. The kiosk unnecessarily re-fetches (minor), or worse, displays a "collection updated" toast for a collection it is not showing (confusing).

If the refetch is expensive (full collection re-render) and both profiles' nightly syncs fire at 03:00, all kiosks thrash simultaneously.

**Why it happens:**
The v2.0 in-process event bus was built profile-aware in data but the SSE broadcast layer may still be topic-blind: `bus.broadcast(event)` to all subscribers regardless of `profile_id`.

**Warning signs:**
- The SSE event payload includes `profile_id` but the broadcast does not filter by it.
- A kiosk bound to profile A shows a "collection updated" toast when profile B syncs.
- The event bus `subscribe()` API does not accept a `profile_id` filter parameter.

**Prevention:**
- **Profile-scoped event bus subscriptions.** The SSE handler subscribes to `bus.subscribe(profile_id=bound_profile_id)` — a per-profile topic. Events published for profile A are only delivered to queues subscribed with `profile_id=A`.
- **Implementation:** the in-process bus uses a `dict[uuid, list[asyncio.Queue]]` keyed by `profile_id`. `publish(event, profile_id)` puts the event only on the queues for that profile. `subscribe(profile_id)` creates a queue in the correct bucket.
- **The `boundary_changed` and `collection_changed` publishers already carry `profile_id` in the payload.** The fix is routing, not payload format.
- **Test:** two SSE clients subscribed to different profiles; trigger a sync for profile A; assert only profile A's client receives the `collection_changed` event.

**Phase to address:**
DEV-02 tech-debt closure (first phase of v2.1, before any SSE-dependent feature). The event bus change is low-risk and unblocks all downstream SSE-dependent v2.1 features.

---

### Pitfall 35: Offline UX trusts `navigator.onLine` and shows false connectivity state

**What goes wrong:**
`navigator.onLine` returns `true` if the Pi is connected to the local network — regardless of whether the GRUVAX server (`lux`) is reachable. On a home LAN, the Pi is almost always connected to the router. But `lux` could be down (Compose restart, Docker update, nightly backup), making `lux` unreachable while `navigator.onLine` remains `true`. The offline banner never shows; the user types a search; the request hangs; the kiosk appears frozen with no feedback.

This is a documented browser quirk: MDN explicitly states that `onLine` "only means the device is connected to some network, not necessarily the internet or your specific server."

**Why it happens:**
`navigator.onLine` is the first tool developers reach for because it's built-in. Its behavior is well-documented but easy to ignore.

**Warning signs:**
- The offline detection logic is `if (!navigator.onLine) showOfflineBanner()`.
- The SSE `EventSource` disconnection does not independently trigger the offline state.
- There is no health probe or heartbeat check to the GRUVAX API.

**Prevention:**
- **Use SSE connection state as the primary offline indicator.** The SSE `EventSource` connects to `lux` directly. When it closes (`EventSource.onerror` or `EventSource.onclose`), the Zustand `connectivity.sseConnected` flag goes `false` and the offline banner appears — within the `sse-starlette` default 15-second ping interval.
- **`navigator.onLine` is used only as a secondary hint** to distinguish "LAN down" (onLine=false) from "server down" (onLine=true, SSE disconnected). The distinction is cosmetic — the banner copy differs ("No network" vs "Server unreachable") — not functional.
- **TanStack Query `networkMode: 'always'`** so queries do not pause waiting for `navigator.onLine` to return true; use the SSE-derived connectivity state to pause queries instead. This prevents the thundering-herd refetch storm when the network reports "online" but the server is still starting up.
- **Do not disable the search input based on `navigator.onLine`.** Disable it based on `!connectivity.sseConnected` instead.

**Phase to address:**
OFF-01 phase. The SSE-connectivity-as-primary-signal is the architectural decision; everything else follows from it.

---

### Pitfall 36: SSE reconnect storm when GRUVAX server restarts after a Compose redeploy

**What goes wrong:**
GRUVAX restarts (Compose redeploy, server update). All SSE `EventSource` connections disconnect simultaneously. The browser's default retry is 3 seconds; with multiple kiosks and an open admin tab, 3–5 clients all reconnect at T+3s. Each reconnect triggers:
1. An SSE subscription (in-process event bus registration).
2. A `GET /api/admin/cubes` refetch (TanStack Query `refetchOnReconnect`).
3. A `/api/search` refetch if there was a pending query.

This is the classic "thundering herd" — 3–5 simultaneous requests at T+3s. On a home LAN with one Uvicorn worker, this is recoverable (not catastrophic). But if nightly sync fires at the same time (03:00 restart + 03:00 sync), the server starts under load from the reconnect storm and the sync.

**Why it happens:**
Browser `EventSource` retry is fixed at 3 seconds by default unless the server sends `retry: <ms>`. Without jitter, all clients retry at the same moment.

**Prevention:**
- **Server sends `retry: <jitter_ms>` on initial SSE response.** With `sse-starlette`, use `ping_message_factory` or the initial event payload to include `retry: <random between 2000 and 8000>`. Each client gets a different retry interval, spreading reconnects over a 6-second window.
- **TanStack Query `refetchOnReconnect: true` is fine for individual clients but should use `staleTime` to avoid redundant refetches.** Set `staleTime` to 30 seconds on the cubes query so a client that reconnects after 10 seconds does not refetch data that was just fetched before the disconnect.
- **The nightly sync starts at 03:00 but only after the server has been stable for 30 seconds** (already implemented in the DST-safe scheduler). This provides a buffer between Compose restart and sync start.
- **Kiosk health: the `systemd` unit's `ExecStartPost` curl healthcheck waits for the SSE endpoint to be ready** before Chromium boots. This prevents a "kiosk starts before server is ready" scenario adding a 4th client to the reconnect storm.

**Phase to address:**
OFF-02 phase. The `retry` jitter is a one-line addition to the SSE setup; TanStack Query staleTime is a per-query config.

---

### Pitfall 37: Stale TanStack Query cache served as fresh after reconnect — user sees old data

**What goes wrong:**
The kiosk loses connectivity at T=0. TanStack Query serves the stale `profile_collection` cache (search works from local Postgres; this is correct per CON-offline-resilience-preserved). At T+30 minutes, nightly sync runs on the server. At T+45 minutes, connectivity restores. TanStack Query's `refetchOnReconnect` triggers a refetch of the search cache. BUT: if the query was marked `stale` while offline (which it was — TanStack Query marks all queries stale after `staleTime` ms), the refetch overwrites the cache with the new data. However, if optimistic updates were applied to the client state during the offline period (e.g., a "recently pulled" list that was modified), those optimistic updates are now wiped by the refetch.

The more concrete failure: the "collection diff" badge (API-04 — "N new records since last sync") was computed from stale data. After reconnect, the diff is re-fetched. But if the UI had already shown "3 new records" and the user had dismissed the badge, the refetch could re-show it.

**Why it happens:**
TanStack Query's optimistic updates are cleared on refetch by default unless `cancelRefetch: true` and explicit rollback logic is implemented. The offline → reconnect transition is the exact scenario where this bites.

**Prevention:**
- **The "collection diff" badge is server-authoritative:** `GET /api/search/diff?since=<last_sync_at>` returns the count. The client dismisses the badge by writing a `dismissed_diff_at` timestamp to `sessionStorage`. On reconnect, if `dismissed_diff_at > last_sync_at`, do not re-show the badge.
- **"Recently pulled" list is in-memory (sessionStorage) — not subject to server refetch.** It is not a TanStack Query cache key; it is pure local state managed by Zustand. The reconnect refetch cannot clobber it.
- **For the search cache:** `staleTime: 60_000` (60 seconds). This means a client that was offline for < 60 seconds after reconnect will NOT refetch. For a client offline for > 60 seconds, a refetch is correct behavior.
- **Do not use optimistic updates for any query that conflicts with server state on reconnect.** Optimistic updates are only appropriate for admin mutations (boundary edits) that are followed immediately by a server confirmation. Search results are not optimistically updated.
- **TanStack Query `networkMode: 'always'`** prevents queries from being paused during offline, which prevents the reconnect-triggered mass refetch from hitting all paused queries at once.

**Phase to address:**
OFF-03/API-04 phase. The `dismissed_diff_at` sessionStorage pattern and the staleTime configuration are the prevention.

---

### Pitfall 38: Invite flow generates an invite link for a profile that already has a PAT

**What goes wrong:**
Owner generates an invite for profile "Alice." Alice completes onboarding. Owner, forgetting, generates another invite for the same profile and sends it to a different person. The second person pastes their PAT, which overwrites Alice's PAT. Alice's collection is now replaced by the second person's collection; her next sync returns different data.

**Why it happens:**
The invite-token generation endpoint does not check whether the target profile already has a connected PAT.

**Warning signs:**
- `POST /api/admin/invite/generate` succeeds even if `profiles.app_token_encrypted IS NOT NULL`.
- The admin invite UI does not show "Already connected" for profiles that have a PAT.

**Prevention:**
- **`POST /api/admin/invite/generate` returns 409 Conflict if the profile already has `app_token_encrypted IS NOT NULL`.** The error message: "This profile already has a connected token. Revoke it first if you want to re-invite."
- **The admin profiles list shows `has_token: true/false`** (from Pitfall 26's `has_token` field), so the owner knows before generating an invite.
- **"Revoke token" admin action** (clears `app_token_encrypted`, sets last sync status to "revoked") is a prerequisite for re-inviting. This is a separate explicit action, not implicit on re-invite.

**Phase to address:**
AUTH-02 phase. The 409 guard is a two-line check in the generate handler.

---

### Pitfall 39: QR code displayed on an HTTP (not HTTPS) LAN URL — bind URL interceptable on LAN

**What goes wrong:**
The QR code encodes `http://gruvax.local:PORT/api/devices/pair/qr/{nonce}`. The admin's phone scans it and sends a GET to that URL. On a home LAN with a network sniffer, this GET is visible in plaintext. The nonce (the secret) transits unencrypted.

For a household with only trusted members, this is a low-severity concern. But the project constraint explicitly mentions "home LAN only; no public exposure" — not "trusted LAN." If any LAN device is compromised (e.g., a smart TV with a vulnerable firmware), the nonce can be captured and used to pair a rogue device within its TTL.

**Why it happens:**
Setting up HTTPS for a home LAN service is an operational burden (self-signed cert, trust installation on all devices). Many developers skip it for LAN-only services.

**Prevention (proportionate to threat):**
- **Option A (recommended for this threat level): Accept HTTP + short-TTL + single-use nonce.** The attack window is 60 seconds (QR auto-rotate interval). A passive LAN sniffer would need to act within that window. For a home with trusted members, this risk is acceptable. Document the decision explicitly.
- **Option B (belt-and-suspenders): Add a confirmation step on the server side.** After the admin's phone GETs the QR nonce URL, the server does NOT immediately bind the device. Instead, it transitions the pairing to a "pending confirmation" state. The admin's phone must then confirm via a separate authenticated admin session action (`POST /api/admin/devices/{id}/confirm`). This prevents a passive sniffer from completing the bind without the admin's involvement.
- **Option C (operational effort justified if any external devices share the LAN):** Deploy a self-signed CA cert for `gruvax.local`, install it on all household devices, serve over HTTPS. The QR URL then encodes `https://gruvax.local:PORT/...`.
- **Regardless of option chosen:** the nonce bind URL must not encode any permanent credential (Pitfall 28's prevention applies).

**Phase to address:**
DEV-04 phase. The decision between Options A/B/C must be made before the QR implementation; document it in the project's Key Decisions.

---

## Minor Pitfalls

### Pitfall 40: "Recently pulled" list (SRCH-09) persists between visitor sessions via localStorage

**What goes wrong:**
The recently-pulled list is implemented as a Zustand store persisted to `localStorage`. Visitor A searches for "Blue Note BLP-4195" — it appears in the recently-pulled list. Visitor B opens the kiosk and sees Visitor A's recent search. This is a privacy concern (PRIV-02 scope) and confusing UX.

**Why it happens:**
Same root cause as Pitfall 31 — `localStorage` is the default for Zustand persistence. The distinction between "persist for this user's session" and "persist forever" must be explicit.

**Prevention:**
- Same fix as Pitfall 31: recently-pulled list in `sessionStorage` or in-memory state only.
- The "reset kiosk" (PRIV-04) action must clear this list.

**Phase to address:**
SRCH-09 phase. Design the storage medium before implementing the feature.

---

### Pitfall 41: Collection diff count (API-04) triggers a spurious "N new records" on first sync after stale period, not a real collection change

**What goes wrong:**
The diff is computed as `count(profile_collection WHERE added_to_cache_at > last_shown_diff_at)`. But if the server was down for 3 days and nightly sync was skipped, then catches up with 3 days of accumulation, the diff shows all 3 days' worth of changes as "new" simultaneously — potentially a large number that startles the user even if no real new records were added (the accumulation was just sync catching up).

**Why it happens:**
The diff is count-based and does not distinguish "newly added to Discogs collection" from "newly added to local cache." A long sync gap inflates the diff count.

**Prevention:**
- **The diff tracks `discogs_added_at`** (the date the member added the record to their Discogs collection), not `cache_added_at`. Compare `discogs_added_at > profiles.last_shown_diff_at`. This correctly counts "new since you last looked" regardless of sync gaps.
- **`last_shown_diff_at` is updated on kiosk load** (or on "dismiss diff badge"), not on sync completion.
- **The diff badge shows "N new records added to your Discogs collection since [date]"** — the date anchors the user's expectation.
- **Cap the displayed count at 99+** to prevent extreme numbers from alarming users.

**Phase to address:**
API-04 phase. The `discogs_added_at` field must be in the `profile_collection` cache (CON-collection-cache-fields allows for additional fields; add it).

---

### Pitfall 42: Aggregate-only stats (PRIV-03) still leak individual query patterns via timing

**What goes wrong:**
PRIV-03 stores only aggregate counts (searches per hour, locate calls per day) not individual query texts. But the aggregate is stored per-hour with high time resolution. An observer with access to the stats table can infer individual sessions: "3 searches in the 14:23 hour, 0 all other hours → someone was searching at 2:23 PM." For a home system, this is low concern. But the intent of PRIV-03 should be explicitly scoped.

**Why it happens:**
Aggregate statistics always leak some temporal information. The question is whether the granularity is fine enough to be a concern.

**Prevention:**
- **Explicitly document PRIV-03's scope:** "No query text stored; aggregate counts at hourly granularity; temporal inference from hourly buckets is acceptable for a home system." This is a documented decision, not an oversight.
- **If higher privacy is required:** bucket to daily granularity only. But for a home system, hourly is fine.
- **The stats table does NOT store `profile_id` on individual query events** — only on the aggregate counter row. This prevents cross-profile comparison.

**Phase to address:**
PRIV-03 phase. The documentation of scope is the mitigation — no code change needed if hourly granularity is acceptable.

---

### Pitfall 43: QR code rendering is blurry or too small on the 7" kiosk screen to be scanned

**What goes wrong:**
The QR code is rendered as a 200×200 CSS pixel element. On the Pi's 7" display (typically 800×480 at 60dpi effective), the QR code is physically 3.3 inches — small but scannable with most phones from normal distance. If the QR is further reduced by padding, margins, or a surrounding "pair your device" dialog, it may drop below the comfortable scan distance for the admin's phone camera.

**Why it happens:**
QR code scannable size depends on physical size and error correction level. A 37-char URL encoded at QR error-correction level M requires at minimum a 25×25 module grid. At 200 CSS pixels, each module is 8 pixels — fine. But if the display is DPI-scaled differently, the physical size drops.

**Prevention:**
- **Minimum 250×250 CSS pixels** for the QR element; use a high-resolution QR library (`qrcode.react` with `size={256}`) and do not further scale down via CSS.
- **Error correction level H** (30% recovery) accommodates slight phone camera angle or screen reflection.
- **Test by scanning with the actual admin phone from normal distance** (arm's length) on the actual 7" display. Document the minimum distance.
- **The auto-rotate countdown (60s) must be shown** so the admin knows how long they have to scan. Use a circular progress indicator around the QR.

**Phase to address:**
DEV-04 phase (frontend QR component). A hardware-in-the-loop test before shipping.

---

## Technical Debt Patterns — v2.1 Additions

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|---|---|---|---|
| Store invite token in `?token=` query param | Simpler URL generation | Pitfall 24 — leaks in referrer and Uvicorn access log | **Never.** Use path segment + `Referrer-Policy: no-referrer`. |
| Skip server-side single-use tracking for invite token | No extra table | Pitfall 25 — token replayable within TTL | **Never.** The `invite_tokens` table is 5 columns; the check is one query. |
| Return `app_token_encrypted` in the profile API response | Easier to debug | Pitfall 26 — owner can decrypt member's PAT; privacy promise broken | **Never.** Return only `has_token: bool`. |
| Accept invite token without validating against discogsography | Faster onboarding | Pitfall 27 — member pastes wrong/over-scoped PAT; first sync fails 24 hours later silently | **Never** without a validation round-trip. The discogsography call is < 200 ms. |
| QR encodes the 4-digit PIN code directly | No extra table | Pitfall 28 — permanent credential visible to anyone with a camera | **Never.** Use a separate, short-lived nonce. |
| Skip `profile_id` in `write_boundary` WHERE clause | Fewer query params | Pitfall 33 — cross-profile boundary corruption; silent data loss | **Never.** This is the v2.0 tech debt item; it must close before v2.1 boundary-editing features. |
| Fan-out all SSE events to all clients | Simpler event bus | Pitfall 34 — wrong kiosk reacts to another profile's events; confusing UX | **Never** in multi-profile mode. Profile-scoped subscriptions are 10 lines of dict keying. |
| Use `navigator.onLine` for offline detection | One line | Pitfall 35 — LAN-connected but server-unreachable shows no offline banner | **Never** as primary signal. Use SSE connectivity as primary. |
| Store search history in `localStorage` | Survives page reload | Pitfall 31/40 — history leaks between kiosk visitors; privacy promise broken | **Never** for search history. `sessionStorage` or in-memory only. |
| Log search query at INFO for debugging | Easier troubleshooting | Pitfall 30 — query text in Docker logs contradicts PRIV-01 | **Never** in production. Debug logging on a feature branch, removed before merge. |

---

## Integration Gotchas — v2.1 Additions

| Integration | Common Mistake | Correct Approach |
|---|---|---|
| **Discogsography PAT validation** | Fire-and-forget storage; validate later | Synchronous validation call before storing; 422 if invalid or wrong scope |
| **Discogsography PAT validation** | Timing out the validation silently, storing the token as-if valid | Return 503 to the invite form; member retries; never store an unvalidated token |
| **Fernet token as invite link** | TTL of 24 hours "to give members time" | 30-minute TTL maximum; single-use DB check is the safety net, not TTL length |
| **QR code nonce** | Generating nonce at page render time (React), not at API call time | Nonce generated server-side on `GET /api/devices/pair/qr` endpoint; React polls to refresh every 60s |
| **TanStack Query offline** | `networkMode: 'offlineFirst'` pauses all queries during offline | `networkMode: 'always'` + SSE-driven manual invalidation; queries run but SSE-derived staleness controls when they refetch |
| **SSE event bus** | `bus.broadcast(event)` to all subscribers | `bus.publish(event, profile_id=X)` → only queues subscribed to profile X receive it |
| **structlog redaction** | Adding redaction as a per-callsite `query="<redacted>"` string | Processor in the pipeline that intercepts any log record with a `query` key and replaces the value; zero per-callsite discipline needed |
| **Zustand persist** | `persist(store)` on the whole store | `persist(store, { partialize: (s) => ({ pendingChangeSet: s.pendingChangeSet }) })` — only wizard draft is persisted, never search history |

---

## Security Mistakes — v2.1 Additions

| Mistake | Risk | Prevention |
|---|---|---|
| Invite token in URL query param | Referrer and access-log leakage of the token | Path segment + `Referrer-Policy: no-referrer`; suppress Uvicorn log for the invite path |
| Reusable invite token (no single-use check) | Any link recipient can complete onboarding | `invite_tokens.used_at` checked server-side with `FOR UPDATE` |
| `ProfileResponse` includes encrypted PAT field | Owner can decrypt member's PAT | Response schema includes only `has_token: bool` |
| QR nonce not rate-limited | Brute-force nonce guessing (low feasibility but cheap to prevent) | 5 attempts / 5 minutes per IP on QR bind endpoint |
| QR auto-rotation interval > 5 minutes | Camera-sniffed nonce remains valid longer | 60-second auto-rotate; old nonce invalidated immediately on rotation |
| `write_boundary` WHERE clause missing `profile_id` | Cross-profile boundary write (silent) | `AND profile_id = :profile_id` in every UPDATE/DELETE; Postgres RLS as defense-in-depth |
| "Reset kiosk" triggers server-side API call without auth | Unauthenticated server state mutation | Reset is client-side only; no API calls; guard: hidden during active admin session |
| Search query text in structlog output | Query text in Docker logs; PRIV-01 promise broken | structlog pipeline processor redacts `query` field before emission |
| Search history in `localStorage` | Persists across kiosk reboots and visitor changes | `sessionStorage` or in-memory Zustand state |

---

## "Looks Done But Isn't" Checklist — v2.1 Additions

- [ ] **AUTH-02 invite flow:** Verify `GET /api/admin/profiles/{id}` response JSON contains no field with "token" or "encrypted" in key or value.
- [ ] **AUTH-02 invite flow:** Verify posting the same invite token twice returns 410 on the second attempt.
- [ ] **AUTH-02 invite flow:** Verify `POST /api/admin/invite/accept` with an invalid PAT (wrong scope) returns 422, not 200.
- [ ] **AUTH-02 invite flow:** Verify `POST /api/admin/invite/generate` returns 409 if the target profile already has `has_token: true`.
- [ ] **AUTH-02 invite flow:** Verify the invite accept page response includes `Referrer-Policy: no-referrer`.
- [ ] **AUTH-02 invite flow:** Verify `docker logs gruvax-api | grep '/invite/'` shows `<redacted>` not the actual token.
- [ ] **DEV-04 QR pairing:** Verify the QR encodes a URL, not a credential (grep the QR payload for any PIN or known secret).
- [ ] **DEV-04 QR pairing:** Verify the QR nonce auto-rotates every 60 seconds (check that the previous nonce is rejected after rotation).
- [ ] **DEV-04 QR pairing:** Verify posting the same QR nonce twice returns 410 on the second attempt.
- [ ] **DEV-04 QR pairing:** Verify the QR bind endpoint returns 429 after 5 rapid attempts.
- [ ] **DEV-04 QR pairing:** Verify both the QR path and 4-digit path use the same `complete_pairing` function and emit identical audit log entries.
- [ ] **DEV-04 QR pairing:** Scan the QR with the actual admin phone from arm's length at the 7" kiosk display — must be readable without moving closer.
- [ ] **OFF-01 offline:** Kill `gruvax-api`; verify the offline banner appears within 20 seconds (one SSE ping interval + buffer).
- [ ] **OFF-01 offline:** While offline, verify search still returns results from cache; verify `navigator.onLine` is NOT the primary offline trigger.
- [ ] **OFF-02 reconnect:** Restart `gruvax-api`; verify all kiosks reconnect within 30 seconds (SSE jitter distributes them).
- [ ] **OFF-02 reconnect:** Verify SSE initial response includes a `retry:` field with jitter (not all clients use the same value).
- [ ] **OFF-03 stale cache:** Reconnect after 90-second outage; verify a fresh data fetch is triggered; verify no optimistic updates are clobbered.
- [ ] **PRIV-01 query privacy:** Run 5 searches; `docker logs gruvax-api | grep radiohead` (or any searched term) returns zero hits.
- [ ] **PRIV-01 query privacy:** Verify Uvicorn access log is not active in production (`--no-access-log` in CMD).
- [ ] **PRIV-02 session history:** Search for X; hard-reload Chromium (simulating kiosk reboot); verify X does not appear in recently-pulled list.
- [ ] **PRIV-04 reset kiosk:** Click "reset kiosk" button; verify browser network tab shows zero API calls.
- [ ] **PRIV-04 reset kiosk:** Verify "reset kiosk" button is hidden when an admin session is active.
- [ ] **Tech debt DEV-02:** Subscribe two SSE clients to different profiles; trigger sync on profile A; verify profile B's client does NOT receive `collection_changed`.
- [ ] **Tech debt write_boundary:** Create two profiles, write boundary for profile A cube (1,1), attempt write from profile B session for same cube (1,1); verify profile A's boundary is unchanged.
- [ ] **SRCH-09 recently pulled:** Verify recently-pulled list is cleared by "reset kiosk"; verify it is NOT in `localStorage` (check `localStorage.getItem('recently-pulled')` is null).
- [ ] **API-04 collection diff:** Verify the diff count is based on `discogs_added_at`, not `cache_added_at`; force a re-sync without adding Discogs records; verify diff count does not change.

---

## Phase-to-Pitfall Mapping — v2.1

| Pitfall | Severity | Owning Phase | Verification |
|---|---|---|---|
| **24** Invite token referrer/log leak | Critical | AUTH-02 (invite backend) | `docker logs` grep; `Referrer-Policy` header present |
| **25** Invite token replay (no single-use) | Critical | AUTH-02 (invite backend) | Second POST returns 410 |
| **26** Owner reads back member PAT | Critical | AUTH-02 (profile response schema) | Profile GET response contains no token field |
| **27** Wrong/over-scoped PAT accepted | Critical | AUTH-02 (invite accept handler) | 422 on invalid/wrong-scope token |
| **28** QR encodes credential not nonce | Critical | DEV-04 (QR implementation) | QR payload is a URL-with-nonce, not a secret |
| **29** QR and PIN paths diverge in security | Critical | DEV-04 (shared `complete_pairing`) | Integration test matrix across both paths |
| **30** Query text in structlog/logs | Critical | PRIV-01 | `docker logs` grep returns zero hits for search terms |
| **31** Session history in localStorage | Critical | PRIV-02 | Hard-reload clears history; Zustand persist excludes it |
| **32** Reset-kiosk as admin bypass | Critical | PRIV-04 | Network tab shows zero API calls on reset |
| **33** `write_boundary` cross-profile write | Major | Tech-debt closure (Phase 6 or first boundary-touching phase) | Two-profile write-isolation integration test |
| **34** SSE fan-out to wrong profile | Major | Tech-debt closure DEV-02 (Phase 6) | Profile-scoped SSE delivery test |
| **35** `navigator.onLine` false connectivity | Major | OFF-01 | Kill server; offline banner appears within 20s |
| **36** SSE reconnect storm | Major | OFF-02 | Restart server; clients spread across 30s window |
| **37** Stale cache clobbers optimistic state | Major | OFF-03/API-04 | Reconnect after 90s outage; diff badge not spuriously re-shown |
| **38** Invite overwrites existing PAT | Major | AUTH-02 | 409 on generate-invite for profile with `has_token: true` |
| **39** QR nonce on HTTP LAN | Major | DEV-04 | Document decision A/B/C before implementation |
| **40** Recently-pulled in localStorage | Minor | SRCH-09 | localStorage null check after reset |
| **41** Diff count inflated by sync gap | Minor | API-04 | Diff based on `discogs_added_at`; re-sync test |
| **42** Aggregate stats temporal inference | Minor | PRIV-03 | Documented scope decision in Key Decisions |
| **43** QR code too small to scan | Minor | DEV-04 (frontend) | Hardware-in-the-loop phone scan test |

---

## Sources

### Authoritative
- [MDN: `navigator.onLine`](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/onLine) — explicitly documents that `onLine` is `true` if connected to any network, not necessarily the target server. HIGH.
- [MDN: Referer header privacy and security concerns](https://developer.mozilla.org/en-US/docs/Web/Privacy/Guides/Referer_header:_privacy_and_security_concerns) — token leakage via referrer; `Referrer-Policy: no-referrer` mitigation. HIGH.
- [Cryptography.io Fernet docs](https://cryptography.io/en/latest/fernet/) — TTL parameter on `decrypt()`; URL-safe base64 encoding. HIGH.
- [TanStack Query: Network Mode](https://tanstack.com/query/v4/docs/react/guides/network-mode) — `networkMode: 'always'` vs `'offlineFirst'`; `refetchOnReconnect` behavior. HIGH.
- [TanStack Query: Important Defaults](https://tanstack.com/query/v4/docs/react/guides/important-defaults) — `refetchOnReconnect: true` default; staleTime semantics. HIGH.
- [Uvicorn settings](https://www.uvicorn.org/settings/) — `--no-access-log` / `access_log=False` option. HIGH.

### Comparative / Verified-with-multiple-sources
- [PortSwigger: Cross-domain Referer leakage](https://portswigger.net/kb/issues/00500400_cross-domain-referer-leakage) — token leakage via referrer; prevention pattern. HIGH.
- [natlas invite/reset token replay issue](https://github.com/natlas/natlas/issues/139) — real-world invite token replay vulnerability; single-use pattern required. HIGH (it's an open bug report).
- [HackerOne Semrush report #342693](https://hackerone.com/reports/342693) — password-reset token leak via referrer; mirrors the invite-token risk. HIGH.
- [TanStack Query optimistic update race discussion #7932](https://github.com/TanStack/query/discussions/7932) — reconnect racing optimistic updates; `cancelQueries` pitfall. MEDIUM.
- [Cendyne.dev: Dual-Device Authorization with QR Codes](https://cendyne.dev/posts/2025-02-17-qr-code-login.html) — QR encodes opaque session reference not credential; server-side binding; TTL and single-use. HIGH.
- [Multi-Tenant Leakage in SaaS (Medium/InstaTunnel)](https://medium.com/@instatunnel/multi-tenant-leakage-when-row-level-security-fails-in-saas-da25f40c788c) — async context leaks, missing WHERE clauses, RLS as defense-in-depth. MEDIUM.
- [FastAPI multi-tenancy discussion #6056](https://github.com/fastapi/fastapi/discussions/6056) — SQLAlchemy tenant scoping patterns; missing profile_id pitfall. MEDIUM.
- [Blocking FastAPI access logs (DEV Community)](https://dev.to/mukulsharma/taming-fastapi-access-logs-3idi) — custom LogFilter to suppress specific paths. MEDIUM.

### Project-specific anchors
- **PROJECT.md v2.1 scope** — AUTH-02, DEV-04, API-04, SRCH-09, OFF-01..04, PRIV-01..04, tech-debt DEV-02, write_boundary.
- **v1.0 PITFALLS.md Pitfall 30 / Technical Debt table** — "search query body logged in plaintext" already flagged; v2.1 PRIV-01 makes it a named requirement.
- **v2.0 PROJECT.md audit `tech_debt`** — DEV-02 SSE immediacy and write_boundary profile scoping are the two flagged items.
- **CON-pat-bearer-flow** — PAT shown plaintext once at mint; hash stored discogsography-side; GRUVAX stores Fernet-encrypted ciphertext. The invite flow must never expose the ciphertext to the owner.
- **CON-rpi-binds-to-one-profile** — device binds to exactly one profile; QR nonce must bind to the same `pairing_codes` table as the 4-digit flow.

---

*Pitfalls research for: GRUVAX v2.1 — Resilience + Privacy + UX Polish (invite-token security, QR pairing, offline UX, query privacy, v2.0 tech-debt closure).*
*Researched: 2026-05-30*

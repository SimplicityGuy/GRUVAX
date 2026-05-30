# Stack Research — GRUVAX v2.1 Additions

**Domain:** v2.1 Resilience + Privacy + UX polish additions to the shipped GRUVAX v2.0 stack
**Researched:** 2026-05-30
**Confidence:** HIGH on backend additions (all verified via PyPI + Context7), HIGH on offline UX recommendation, MEDIUM on frontend QR choice (both candidates are viable; rationale is clear)

This file covers ONLY the net-new stack decisions for v2.1. The existing validated stack (Python 3.13, FastAPI 0.136, psycopg 3.2, SQLAlchemy 2.0, Alembic 1.18, itsdangerous 2.2, sse-starlette 2.x, React 19, Vite 8, TanStack Query 5, Zustand 5, GSAP) is NOT re-examined here.

---

## Summary of Net-New Additions

| Feature | Addition | Layer | Why |
|---------|----------|-------|-----|
| DEV-04 QR pairing | `react-qr-code` 2.0.21 | Frontend only | Render QR in-browser from the pairing URL; no server dependency |
| AUTH-02 invite tokens | `itsdangerous.URLSafeTimedSerializer` (already present) + `invite_tokens` DB table | Backend | TTL-signed tokens from existing dep; DB row enforces single-use |
| OFF-01..04 offline UX | TanStack Query `networkMode: 'offlineFirst'` + custom `useBackendOnline` hook + native `EventSource` auto-reconnect | Frontend | No new package; already-present primitives are sufficient |
| PRIV-01..04 privacy | `sessionStorage` (browser built-in) | Frontend | Zero-install; clears automatically on tab/browser close |

**No new backend Python packages are required for v2.1.** All four feature areas are served by existing dependencies plus one frontend package.

---

## 1. QR-Code Generation (DEV-04)

### Decision: Frontend-only with `react-qr-code`

**Do not generate QR codes server-side.** The kiosk already knows the pairing URL — it owns both the display and the session. Generating a PNG on the server and shipping it to the browser adds an HTTP round-trip, an image decoding step, and a new backend endpoint, in exchange for nothing. The QR content is not secret (it encodes the same 4-digit code + server URL the kiosk already shows in text).

| Library | Version | Status | Why / Why Not |
|---------|---------|--------|---------------|
| **`react-qr-code`** | **2.0.21** | **Recommended** | Actively maintained (last publish 2026-04-29, npm last confirmed). Outputs pure SVG — scales perfectly on any DPI without blurriness on the Pi's 7" screen. Zero runtime dependencies. 340+ dependents. MIT licensed. |
| `qrcode.react` | 4.2.0 | Not recommended | Last publish 2024-12-11 — over 17 months without a release. Still functional, but `react-qr-code` is the actively-maintained successor with equivalent API surface. |
| `python-qrcode[pil]` | 8.2 | Do not add | Server-side generation for this use case is overcomplicated. Adds Pillow to the runtime image for a feature that runs better client-side. Only warranted if you need to embed QR codes in PDF reports or email — neither applies here. |
| `qrcode` (pure Python, SVG mode) | 8.2 | Do not add | Same rationale as above. The SVG factory is useful for server-rendered documents; not for a kiosk SPA. |

### Integration

`react-qr-code` is a single `<QRCode>` component. The kiosk's existing pairing screen renders the 4-digit code as text today (v2.0). In v2.1 it renders both:

```tsx
import QRCode from 'react-qr-code';

// pairingUrl = `http://gruvax.local:8000/pair?code=1234&device=<fingerprint>`
<QRCode value={pairingUrl} size={180} level="M" />
```

The `level="M"` error-correction level handles up to ~15% damage — adequate for a phone camera reading a clean screen. `size={180}` fits the existing pairing modal without layout changes.

**Do NOT add** `qrcode.react`, `@zxing/library`, `html5-qrcode`, or any QR *scanner* library — the kiosk renders the code, the admin's phone scans it with its native camera app.

---

## 2. One-Time Invite Tokens (AUTH-02)

### Decision: `itsdangerous.URLSafeTimedSerializer` + `invite_tokens` DB table

`itsdangerous` 2.2.0 is already a transitive dependency of `starlette.SessionMiddleware` (already in the lockfile). No new package is needed.

`URLSafeTimedSerializer` provides:
- Cryptographic signing with HMAC-SHA1 (configurable to SHA-512)
- Built-in timestamp embedding (`dumps()` includes the signing time)
- `max_age` on `loads()` enforces TTL — raises `SignatureExpired` if the token is older than the threshold
- URL-safe base64 encoding — the token is embeddable in a URL query parameter without percent-encoding

**Critical limitation:** `itsdangerous` tokens are NOT single-use by themselves. The signature is stateless — the same token verifies successfully on every call until it expires. Single-use enforcement requires a database-side "consumed" flag.

### Required: `invite_tokens` Table

```sql
-- Alembic migration
CREATE TABLE gruvax.invite_tokens (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash  text NOT NULL UNIQUE,   -- SHA-256 of the raw token string
    profile_id  uuid NOT NULL REFERENCES gruvax.profiles(id) ON DELETE CASCADE,
    created_by  text NOT NULL,          -- 'owner' sentinel or future user ref
    expires_at  timestamptz NOT NULL,
    used_at     timestamptz,            -- NULL = unused; NOT NULL = consumed
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON gruvax.invite_tokens (token_hash) WHERE used_at IS NULL;
```

### Flow

1. Owner requests an invite link via the admin UI → server calls `URLSafeTimedSerializer(secret_key, salt='invite').dumps({'profile_id': str(profile_id)})`, writes the SHA-256 of the token to `invite_tokens`, sets `expires_at = now() + 24h`.
2. Server returns the signed URL (e.g. `http://gruvax.local:8000/invite?token=<token>`).
3. Recipient opens the URL in their browser, pastes their own Discogs PAT into a minimal form.
4. Server: `loads(token, max_age=86400)` — raises `SignatureExpired` if >24h. Look up `token_hash` in `invite_tokens` where `used_at IS NULL` — if absent or already used, reject. If valid: store the Fernet-encrypted PAT on the profile row, set `used_at = now()`.

**TTL:** 24 hours is the right default for a household. The owner sends the link to a family member who acts within the day. Configure via `Settings` if needed — the `expires_at` column makes this trivial to adjust.

**Why not JWT?** JWT is stateless; you cannot revoke a JWT without a denylist (which is the same DB table you'd need anyway). `itsdangerous` is already present; introducing `python-jose` or `PyJWT` for this single use case adds a package for no benefit.

**Why not a random UUID token stored in plain?** Also valid. The `itsdangerous` approach has the advantage that the signature check catches tampering before hitting the DB, reducing unnecessary DB lookups for malformed tokens. The difference is small — either approach works. Signed tokens are chosen because the library is already present.

**Do NOT add** `PyJWT`, `python-jose`, `authlib`, `fastapi-users`, or any OAuth library for this feature.

---

## 3. Offline / Reconnect UX (OFF-01..04)

### Decision: No new package — compose existing primitives

The v2.1 offline requirements are:
- OFF-01: detect backend/LAN loss
- OFF-02: graceful degraded mode (search from cache, locate from cache — already works; just need a UI banner)
- OFF-03: auto-reconnect when connectivity returns
- OFF-04: offline banner, dismissible

All four are achievable with what is already in the project:

**TanStack Query `networkMode: 'offlineFirst'`** (no package addition)

```tsx
// QueryClient config — set once at app root
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      networkMode: 'offlineFirst',  // run the query; pause retries while offline
      staleTime: 5 * 60 * 1000,
      gcTime: 30 * 60 * 1000,
      retry: 3,
    },
  },
});
```

`offlineFirst` lets queries run on first mount (hits the local cache), then pauses retries when the browser detects offline — exactly what a kiosk with a local cache needs. It does not block rendering on network state.

**Custom `useBackendOnline` hook** (no package; ~25 lines)

`navigator.onLine` is unreliable for a home LAN scenario: it reflects "has a network interface" not "can reach the GRUVAX server". A kiosk connected to WiFi but with the Docker host restarted would show `navigator.onLine === true` while being effectively offline to the app.

The correct approach for a LAN-only deployment is a lightweight periodic health check against the server:

```tsx
// hooks/useBackendOnline.ts — no external package required
function useBackendOnline(intervalMs = 10_000) {
  const [online, setOnline] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const res = await fetch('/healthz', { signal: AbortSignal.timeout(3000) });
        if (!cancelled) setOnline(res.ok);
      } catch {
        if (!cancelled) setOnline(false);
      }
    };
    check();
    const id = setInterval(check, intervalMs);
    return () => { cancelled = true; clearInterval(id); };
  }, [intervalMs]);

  return online;
}
```

`/healthz` already exists (Phase 8 of v1.0). `AbortSignal.timeout(3000)` (Web API, no polyfill needed in Chromium) bounds the check to 3 seconds. A 10-second poll interval means the banner appears within 10–20 seconds of backend loss — acceptable for a household kiosk.

**Zustand offline slice** (already in project)

```tsx
// Store already exists; add one field:
interface KioskStore {
  backendOnline: boolean;
  setBackendOnline: (v: boolean) => void;
}
```

The offline banner component reads from Zustand and renders based on `backendOnline`. The `useBackendOnline` hook calls `setBackendOnline` on state transitions.

**SSE auto-reconnect** (native `EventSource` behavior, no code required)

The browser's native `EventSource` API automatically reconnects with a 3-second default retry interval when the connection drops. The existing `sse-starlette` backend sends `retry:` fields that can tune this. For the GRUVAX SSE channel (`/api/events/{profile_id}`), native reconnect is sufficient — no reconnect library needed.

When the SSE connection drops and the health check sees the backend offline, suppress the SSE reconnect noise in the UI (don't show a "reconnecting" spinner on top of the offline banner — that's redundant). When health check comes back positive, the SSE reconnect will have already happened automatically.

### Why NOT `vite-plugin-pwa` / Workbox

`vite-plugin-pwa` + Workbox is the right tool when you need:
- Installability as a PWA (home screen icon, standalone window)
- Aggressive precaching of static assets for full offline operation without a server
- Background sync for mutation queuing while offline
- Push notifications

GRUVAX needs none of these. The kiosk always has the server on the same LAN — the "offline" state is a temporary disruption (server restart, network blip), not a design intent to operate without a server. The search/locate results come from the server cache; the frontend itself is served by FastAPI's `StaticFiles` and caches in Chromium's standard HTTP cache between loads.

Adding a service worker intercepts ALL requests, which complicates the SSE connection (service workers do not support `EventSource` in the intercepted context without explicit passthrough), adds a second request-handling layer to debug, and requires careful cache invalidation strategy on every deploy. The complexity-to-benefit ratio is negative for this use case.

**Do NOT add** `vite-plugin-pwa`, `workbox-window`, `workbox-precaching`, `workbox-routing`, or any service worker library.

---

## 4. Privacy / Session-Only History (PRIV-01..04)

### Decision: `sessionStorage` (browser built-in, zero install)

PRIV requirements:
- PRIV-01: session-only search history (clears when tab/browser closes)
- PRIV-02: no server-side query-text persistence
- PRIV-03: aggregate-only stats (already enforced server-side in v2.0 `record_stats`)
- PRIV-04: no-PIN "reset kiosk" (clears client state without server auth)

**`sessionStorage`** is the correct storage primitive for PRIV-01 and PRIV-04:

- Tied to the browser tab/session; cleared automatically when Chromium is restarted (which happens on every kiosk reboot via the `systemd --user` unit restart)
- 5 MB limit — more than adequate for a list of recent searches (strings)
- Synchronous API — no async complexity for a read/write of a few strings
- Isolated per origin — no cross-tab leakage
- Not persisted to disk in the same way as `localStorage` (important for a shared kiosk)

```tsx
// Recently pulled list (SRCH-09) + search history (PRIV-01)
// Stored as JSON arrays in sessionStorage — no library needed
const RECENT_KEY = 'gruvax:recent_searches';

function getRecentSearches(): string[] {
  try {
    return JSON.parse(sessionStorage.getItem(RECENT_KEY) ?? '[]');
  } catch {
    return [];
  }
}

function addRecentSearch(query: string): void {
  const recent = getRecentSearches();
  const deduped = [query, ...recent.filter(q => q !== query)].slice(0, 20);
  sessionStorage.setItem(RECENT_KEY, JSON.stringify(deduped));
}
```

PRIV-02 (no server-side query text) is a backend implementation constraint, not a stack question — the `/api/search` handler must not log the `q` parameter and must not write it to any DB table. This is enforced at code-review time, not by a library.

PRIV-04 (reset kiosk) clears `sessionStorage` (and optionally the TanStack Query cache) then redirects to the home route — no server call, no PIN required. The "reset" is purely client-side state disposal.

**Why not `localStorage`?** `localStorage` persists across browser restarts, which violates PRIV-01. On a shared kiosk, a visitor's searches surviving to the next session is the exact privacy failure the requirement exists to prevent.

**Why not `IndexedDB`?** IndexedDB is the right choice for structured offline storage of large datasets (think: a local copy of the collection for full offline search). For a list of 10–20 recent search strings, IndexedDB's async API and transaction model is unnecessary complexity. The data is session-scoped and tiny.

**Why not Zustand `persist` middleware?** Zustand's `persist` middleware defaults to `localStorage`. You CAN configure it to use `sessionStorage` (via `storage: createJSONStorage(() => sessionStorage)`), and that would also work. The raw `sessionStorage` approach is simpler because it avoids tying the persistence decision into the Zustand store shape. Use whichever is more consistent with how the rest of the app manages local state — both are zero-install options.

**Do NOT add** `idb`, `localforage`, `dexie`, or any IndexedDB wrapper for this use case.

---

## Net-New Installation

```bash
# Frontend — one package added
npm install react-qr-code

# Backend — no new packages; itsdangerous is already a transitive dep
# New Alembic migration needed for invite_tokens table (no pip changes)
```

---

## What NOT to Add (v2.1 Explicit Exclusions)

| Do NOT Add | Why | What to Use Instead |
|------------|-----|---------------------|
| `python-qrcode` | Server-side QR generation unnecessary; adds Pillow bloat | `react-qr-code` (frontend) |
| `qrcode.react` | Effectively unmaintained since Dec 2024 | `react-qr-code` 2.0.21 |
| `PyJWT` / `python-jose` | No JWT need; `itsdangerous` is already present | `URLSafeTimedSerializer` + `invite_tokens` table |
| `authlib` | OAuth machinery; invite tokens are a much simpler problem | `itsdangerous` + DB row |
| `fastapi-users` | Multi-user auth for a single-PIN + invite-token flow | `SessionMiddleware` + `invite_tokens` table |
| `vite-plugin-pwa` | Service workers complicate SSE, add cache invalidation overhead, solve a "full offline" problem GRUVAX doesn't have | TanStack Query `offlineFirst` + `useBackendOnline` hook |
| `workbox-window` / `workbox-precaching` | Same rationale as `vite-plugin-pwa` | — |
| `localforage` / `dexie` / `idb` | IndexedDB is the wrong scope for session-only search history | `sessionStorage` (built-in) |
| `use-online` / `react-use` network hooks | Thin wrappers around `navigator.onLine` — unreliable for LAN-only detection | Custom `useBackendOnline` with `/healthz` ping |
| `react-use` (full lib) | Pulls in ~100 hooks for 2–3 needed ones | Write the 2–3 needed hooks directly (~25 lines each) |

---

## Alternatives Considered

| Feature | Recommended | Alternative | Why Not |
|---------|-------------|-------------|---------|
| QR generation | `react-qr-code` (frontend, SVG) | `python-qrcode` server-side PNG | Unnecessary server round-trip; client has all data it needs |
| QR generation | `react-qr-code` | `qrcode.react` | Last release 2024-12-11; `react-qr-code` is actively maintained successor |
| Invite tokens | `itsdangerous` + DB table | Random UUID in DB only | Both work; `itsdangerous` adds tamper-detection before hitting DB for free (lib already present) |
| Invite tokens | `itsdangerous` + DB table | JWT (python-jose / PyJWT) | JWT is stateless — still needs a denylist table to enforce single-use, defeating the stateless advantage |
| Offline detection | Custom `/healthz` hook | `navigator.onLine` events only | `navigator.onLine` detects "has network interface", not "can reach GRUVAX server" — unreliable on home LAN |
| Offline detection | Custom hook | `vite-plugin-pwa` + Workbox | Workbox solves "fully offline" PWA; GRUVAX needs "detect disruption + reconnect", a much simpler problem |
| Privacy history | `sessionStorage` | `localStorage` | `localStorage` persists across browser restarts — violates PRIV-01 |
| Privacy history | `sessionStorage` | Zustand `persist` + `sessionStorage` storage | Both work; raw `sessionStorage` is simpler for this case |

---

## Version Compatibility Notes

| Addition | Requires | Notes |
|----------|----------|-------|
| `react-qr-code` 2.0.21 | React 16+ | Compatible with React 19. Pure SVG, no canvas requirement. |
| `URLSafeTimedSerializer` | `itsdangerous>=2.2` (already pinned) | `loads(token, max_age=86400)` raises `SignatureExpired` on TTL breach; `BadSignature` on tampering. Catch both as `BadData`. |
| `invite_tokens` table | Alembic + Postgres | New migration; FK to `profiles.id` with `ON DELETE CASCADE`. Index on `token_hash WHERE used_at IS NULL` for fast lookup. |
| TanStack Query `offlineFirst` | TanStack Query v5 (already in use) | `networkMode: 'offlineFirst'` in `QueryClient` defaultOptions. No API changes to individual `useQuery` calls unless you need per-query override. |
| `sessionStorage` | Chromium (already the kiosk browser) | No polyfill needed. Available in all modern browsers since IE8. Cleared on Chromium restart (happens on every kiosk reboot). |

---

## Sources

- [react-qr-code on npm](https://www.npmjs.com/package/react-qr-code) — version 2.0.21, last published 2026-04-29 — HIGH
- [qrcode.react on npm](https://www.npmjs.com/package/qrcode.react) — version 4.2.0, last published 2024-12-11 — HIGH (confirmed stale)
- [python-qrcode on PyPI](https://pypi.org/project/qrcode/) — version 8.2, released 2025-05-01, Python 3.9–3.13 — HIGH
- [itsdangerous Context7 docs](/pallets/itsdangerous) — `URLSafeTimedSerializer`, `max_age`, `SignatureExpired`, `BadData` — HIGH
- [itsdangerous PyPI](https://pypi.org/project/itsdangerous/) — version 2.2.0 current — HIGH
- [TanStack Query v5 Context7 docs](/tanstack/query) — `networkMode: 'offlineFirst'`, `networkMode: 'always'`, `onlineManager` — HIGH
- [TanStack Query Network Mode docs](https://tanstack.com/query/v5/docs/react/guides/network-mode) — three modes confirmed, `offlineFirst` behavior documented — HIGH
- [MDN Navigator.onLine](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/onLine) — known unreliability for LAN scenarios documented — HIGH
- [vite-plugin-pwa Context7 docs](/websites/vite-pwa-org_netlify_app) — service worker capabilities and scope confirmed — MEDIUM (service worker confirmed as the wrong tool for this case)
- [Browser storage comparison (multiple sources)](https://dev.to/arnavsharma2711/browser-storage-explained-localstorage-vs-sessionstorage-vs-indexeddb-vs-cookies-283k) — `sessionStorage` session-scoped behavior confirmed — MEDIUM

---

*Stack research for: GRUVAX v2.1 Resilience + Privacy + UX polish (net-new additions only)*
*Researched: 2026-05-30*

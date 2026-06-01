# Phase 8: QR Pairing + Privacy + Recently-Pulled - Context

**Gathered:** 2026-06-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Three loosely-coupled kiosk-facing capabilities, all session-scoped:

1. **DEV-04 — QR pairing alongside the 4-digit PIN.** The kiosk pairing screen shows a
   scannable QR next to the existing 4-digit code. Scanning opens the admin bind page
   prefilled with the current code; both the scan path and the typed path call the
   **same bind endpoint** and emit **identical audit entries**. The QR encodes a bind
   **URL carrying an opaque short-TTL code, never a credential**.

2. **SRCH-09 — session-only recently-pulled list.** The kiosk keeps a short chip list of
   records the user has located, kept only for the current session. No server-side
   persistence.

3. **PRIV-01..04 — privacy guarantees.** Search history is session-only and never
   persists across a Chromium restart; a **no-PIN "Reset kiosk"** affordance clears the
   local session client-side only; the server **never logs raw query text** (PRIV-02) and
   record stats stay **aggregate-only** (PRIV-03) — both de-facto met since v1.0 and
   **formalized + CI-test-locked** here.

**Not in this phase** (own phases): offline/reconnect UX (OFF-*, Phase 9); shelf
fill-overview (UX-01, Phase 10); QR for the *invite/redeem* link (deferred from Phase 7 —
revisit once the QR library lands here); OAuth2 device grant (AUTH-01, v2.2).
</domain>

<decisions>
## Implementation Decisions

### Locked upstream (from REQUIREMENTS.md / ROADMAP.md — do NOT re-litigate)
- **L-01:** QR transport is **HTTP + a short-TTL single-use code on the home LAN** —
  proportionate to the home threat model. Document as a **Key Decision** (Pitfall 39). No
  TLS termination, no HTTPS requirement for v2.1.
- **L-02:** QR encodes a bind **URL with an opaque short-TTL code, never a credential**
  (not the PIN, not a PAT).
- **L-03:** Both pairing paths (scan + typed code) call the **same bind function** and
  emit **identical audit log entries** (success criterion 1).
- **L-04:** PRIV-02 (no raw query in logs) and PRIV-03 (aggregate-only stats) are
  **already true** in the codebase — this phase formalizes them and adds the CI test that
  asserts no plaintext query text appears in `docker logs gruvax-api`. No behavior change
  beyond test-locking + (re)confirming uvicorn access-log suppression.
- **L-05:** PRIV-04 "Reset kiosk" is **client-side only** — zero API calls, no device
  unbind.

### QR pairing (DEV-04)
- **D-01:** The QR encodes a bind-page URL carrying the **existing 4-digit pairing code**
  (the same code, same 5-min TTL, same `pairing_codes` row). It does **not** introduce a
  separate opaque nonce or a faster rotation. The 4-digit code *is* the "opaque short-TTL
  code" the requirement asks for. This makes "both paths → same `complete_pairing()` /
  identical audit" automatic. *(Supersedes the open-decisions "60s nonce rotation" note —
  a second code path is unjustified ceremony for an admin-gated, home-LAN bind.)*
- **D-02:** Scanning lands the phone on the **PIN-gated admin bind page** (the existing
  admin devices bind flow), prefilled with the code. If the phone has no admin session it
  is prompted for the **PIN first**, then completes the bind. This **preserves the
  current bind security model** — the public kiosk QR cannot bind a device without the
  admin PIN.
- **D-03:** The QR **re-renders exactly when the 4-digit code auto-rerolls** (the 5-min
  reroll already implemented in `PairView.tsx`). One source of truth; no separate timer.
- **D-04:** After landing prefilled, pairing completes via an **explicit one-tap confirm**
  ("Pair this device"), not auto-submit — prevents accidental binds from a stray scan and
  matches "the admin completes pairing".

### Recently-pulled list (SRCH-09)
- **D-05:** A record enters the list **only on a successful locate** (a search that
  resolves to a cube highlight) — not on every committed search. Matches the
  "recently-*pulled*" intent; typo/no-result searches never appear.
- **D-06:** Tapping a chip **re-locates that record** (re-runs the locate + re-highlights
  the cube) — the list is a fast "jump back" shortcut, not decoration.
- **D-07:** Cap **~8 chips, most-recent-first, deduped** (re-locating an existing record
  moves it to the front, no duplicate). Sized for the 7" kiosk.
- **D-08:** Renders as a **persistent horizontal chip strip below the search/cube-result
  area**, visible once non-empty. (Exact visual is UI-phase; this fixes the layout slot.)

### Reset kiosk (PRIV-04)
- **D-09:** "Reset kiosk" clears the **recently-pulled list + the current search/cube
  result** (the local UI session) only. The device **stays paired** and the **bound
  profile stays selected** — no return to the picker, no unbind, zero API calls.
- **D-10:** The button is **hidden when this browser has an active admin session**,
  detected **client-side** via the same SPA's `adminStore.isLoggedIn`. (NOT a server-wide
  `admin_active` flag — that would wrongly hide the kiosk Reset whenever the owner is in
  admin on their phone.)
- **D-11:** Tapping Reset shows a **lightweight confirm** ("Reset kiosk? This clears your
  recent searches.") before wiping — guards against an accidental tap.
- **D-12:** Placement is **subtle / low-emphasis** (corner or footer) — a rare
  exit/privacy action, kept off the search-first primary surface. (Final visual is
  UI-phase.)

### History clear triggers (PRIV-01 / SRCH-09)
- **D-13:** The list is **`sessionStorage`-backed** — it survives an accidental reload
  within the same browser session but clears on tab close, browser session end, and a
  **hard Chromium restart** (success criterion 2). The Zustand `persist` slice **must
  explicitly exclude** the history (PRIV-01).
- **D-14:** Add a **~15-minute kiosk idle timeout** that triggers a session clear
  (SRCH-09 requires an idle-clear trigger; the kiosk has none today). 15 min is forgiving
  of a user who pauses to walk to the shelf.
- **D-15:** On idle timeout **and** session end, the kiosk **returns to the resting screen**
  — clears both the recently-pulled list and the current search/result so the previous
  visitor's lookup isn't left on display. Device stays paired/bound (same scope as D-09).

### Claude's Discretion (resolve at research/plan/UI time — not user decisions)
- **QR library choice:** frontend `react-qr-code` (render in the SPA) vs a backend
  `qrcode` endpoint. Lean frontend-only since the kiosk already renders the code; the QR
  is just a second encoding of the same bind URL. Flag for researcher.
- **PRIV-02 CI test shape:** how to assert "no plaintext query in logs" — likely run a
  search against the app, capture the structlog/stdout stream (or the in-process log ring
  + uvicorn access log), and assert the query term is absent. Reuse the existing
  `redact_dscg_tokens` processor pattern if any new `q`-adjacent logging is added.
- **Identical-audit plumbing:** ensure the QR scan path produces a byte-identical audit
  entry to the typed path (same `complete_pairing` call site, same fields).
- **Chip content:** what each chip shows (artist / title / catalog number) and truncation
  on the 7" display — UI-phase detail. Use DM Mono for catalog numbers per the design
  language.
- **Idle-timer reset semantics:** which interactions reset the 15-min timer (any
  touch/search) — builder discretion; reset on any user interaction.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — **DEV-04** (QR pairing), **SRCH-09** (session-only
  recently-pulled), **PRIV-01/02/03/04** (session-only history; no raw-query logging;
  aggregate-only stats; no-PIN reset). Also the "Open Decisions" row locking
  HTTP + short-TTL single-use code for QR on the home LAN.
- `.planning/ROADMAP.md` § "Phase 8: QR Pairing + Privacy + Recently-Pulled" — goal,
  the four success criteria, and the Phase 6 dependency (DEV-05 SSE consumer wired before
  QR adds a second pairing path).
- `.planning/PROJECT.md` — core value (≤200 ms search), security posture (single PIN,
  home-LAN-only), repo-hygiene constraints.

### Design language (UI hint: yes)
- `design/gruvax-design-language.md` — Nordic Grid spec; the Kallax cube unit, lit/dim
  cell states, LED-physics motion, plain-language voice for the Reset confirm + any
  pairing copy.
- `design/gruvax-design-tokens.css` / `.json` — consume tokens, never hardcode hex.
  DM Mono for catalog numbers on the recently-pulled chips.

### Prior-phase decisions to honor
- `.planning/phases/07-member-self-connect-collection-diff/07-CONTEXT.md` — Phase 7
  deferred *invite-QR* and the QR library to this phase (DEV-04); Nordic-Grid
  plain-language redeem/error copy precedent (D-11).
- `.planning/phases/06-safe-boundaries-live-device-lifecycle/06-SECURITY.md` — the
  per-profile SSE bus + device-lifecycle threat model the QR second-pairing-path must not
  weaken.

No external ADRs — design decisions are captured in `<decisions>` above and the Key
Decision (L-01) is documented inline.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Pairing-code generation** — `src/gruvax/api/devices.py:52-116`
  (`generate_pairing_code()`: 4-digit `secrets.randbelow`, 5-min TTL, auto-issues the
  HttpOnly fingerprint cookie). The QR is a second encoding of *this same* code (D-01).
- **Bind endpoint** — `src/gruvax/api/admin/devices.py:240-336`
  (`POST /api/admin/devices/bind`: atomic first-wins consume
  `UPDATE pairing_codes SET consumed_at=NOW() WHERE code=%s AND consumed_at IS NULL AND
  expires_at > NOW() RETURNING fingerprint`, then 3-step device UPSERT; rate-limited
  10/5min/IP). **Both pairing paths must funnel through here** (L-03). This is the single
  `complete_pairing()` call site for identical audit entries.
- **Kiosk PairView** — `frontend/src/routes/kiosk/PairView.tsx:48-323`: fetches the code,
  runs the 5-min countdown + **auto-reroll** (lines 118-176), polls `GET /api/devices/me`
  every 3 s. The QR mounts here and re-renders off the same reroll (D-03).
- **Device frontend API** — `frontend/src/api/devices.ts:61-93`
  (`postPairingCode()`, `getDeviceMe()`, `adminFetch()` for the CSRF-bearing admin bind).
- **structlog + redaction** — `src/gruvax/logging_config.py:106-189` (processor chain;
  uvicorn access log already suppressed to WARNING at line 188; LogRingHandler attached
  to the `gruvax` logger only) and `src/gruvax/discogsography/log_redactor.py:23,28-53`
  (`redact_dscg_tokens` recursive masking). The PRIV-02 CI test asserts against this
  stream; reuse the redaction-processor pattern if any new `q`-adjacent log is added.

### Established Patterns
- **`q` is already never logged** — `src/gruvax/api/search.py:131` (PRIVACY comment),
  `:149-152` logs `release_id` only; `src/gruvax/api/locate.py:224` identical. PRIV-02/03
  are de-facto met (L-04); Phase 8 adds the test, not the behavior.
- **Zustand stores** — kiosk search store `frontend/src/state/store.ts` and session store
  `frontend/src/state/sessionStore.ts` are **not** wrapped in `persist` (ephemeral).
  The admin store `frontend/src/state/adminStore.ts:76-120` IS persisted with
  `partialize` (only `pendingChangeSet` + `reshuffleDraft`, localStorage key
  `gruvax-admin`). **The recently-pulled slice must be `sessionStorage`-backed and
  excluded from any localStorage persist** (D-13 / PRIV-01).
- **`adminStore.isLoggedIn`** is in-memory (cookie-authoritative) — the kiosk Reset
  button reads it directly to hide during an admin session (D-10).

### Integration Points
- **New QR render in `PairView.tsx`** — add a QR (likely `react-qr-code`) encoding the
  bind URL with the current code; re-render on the existing reroll effect.
- **Bind landing route** — the scan target is the existing PIN-gated admin devices/bind
  page (`/admin/devices`, App.tsx:143+), prefilled from a query param; phone hits the PIN
  gate if unauthenticated (D-02), then one-tap confirm (D-04). May need a small
  prefill-from-query affordance on the admin devices bind UI.
- **New recently-pulled slice** — a `sessionStorage`-backed store feeding a chip strip in
  `frontend/src/routes/kiosk/KioskView.tsx` (below the result area); populated on
  successful locate (D-05), tap re-locates (D-06).
- **Idle timeout + Reset** — kiosk-level ~15-min idle timer (none today) + a subtle Reset
  affordance in KioskView; both clear the search store + recently-pulled slice and return
  to the resting screen (D-09/D-14/D-15).
- **PRIV-02 CI test** — new test under the backend test suite asserting a searched term
  does not appear in captured logs; confirm uvicorn access-log suppression stays in place.

### Caveats
- The kiosk SPA and admin SPA are the **same app** (App.tsx routes) — `adminStore` is
  reachable from the kiosk view, which is why D-10's client-side flag works. But the admin
  cookie is **per-browser**: on the Pi kiosk, the owner does admin from their phone, so
  the kiosk's `isLoggedIn` is normally false — exactly the case where the Reset button
  *should* show. Do not substitute a server-wide flag.
- No QR library exists in `frontend/package.json` or the Python deps yet — adding one is
  part of this phase.
</code_context>

<specifics>
## Specific Ideas

- The QR is a convenience encoding of the *same* 4-digit code the admin would otherwise
  type — keep the two paths literally one bind function so audit entries are identical.
- Reset-kiosk copy and the confirm dialog use the Nordic-Grid plain-language voice (no
  jargon), consistent with Phase 7's redeem-error copy.
- Recently-pulled chips should render catalog numbers in DM Mono per the design language.
</specifics>

<deferred>
## Deferred Ideas

- **QR for the invite/redeem link (Phase 7 AUTH-02)** — was deferred to "once the QR
  library lands." The library lands here; adding invite-QR is still its own follow-up, not
  part of Phase 8's DEV-04 scope. Note for a future polish phase.
- **Separate faster-rotating opaque nonce for the QR** — considered (open-decisions "60s
  nonce") and rejected (D-01) for this phase; revisit only if the home threat model
  changes or QR moves off the LAN.
- **Server-persisted / set-level search history** — explicitly out of scope (PRIV-01/03;
  REQUIREMENTS "Out of Scope").

None of the above belong in Phase 8.
</deferred>

---

*Phase: 8-qr-pairing-privacy-recently-pulled*
*Context gathered: 2026-06-01*

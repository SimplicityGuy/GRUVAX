# Phase 7: Member Self-Connect + Collection Diff - Context

**Gathered:** 2026-05-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Two capabilities, both per-profile:

1. **AUTH-02 — Member self-connect via invite token.** The owner issues a one-time,
   time-limited **invite link** for a profile. A household member opens it (no GRUVAX
   login account is created), pastes **their own** discogsography PAT into a
   GRUVAX-served form, and the PAT is stored Fernet-encrypted on that profile. The
   owner never sees the raw token — profile responses expose only `has_token: bool`.
   Invite is single-use (`consumed_at`) and TTL-bounded; expired/used/invalid redeems
   show a clear error.

2. **API-04 — "N new records since last sync".** After any sync (nightly or manual),
   the kiosk and admin surface a per-profile count of newly-arrived records. The count
   is computed inside the existing staging-swap sync and delivered on the
   `collection_changed` SSE payload. **Count only** — which specific records changed is
   out of scope.

**Not in this phase** (own phases): QR pairing (DEV-04, Phase 8), recently-pulled list
(SRCH-09, Phase 8), offline UX (OFF-*, Phase 9), OAuth2 device grant (AUTH-01, v2.2).
</domain>

<decisions>
## Implementation Decisions

### Locked upstream (from REQUIREMENTS.md — do NOT re-litigate)
- **L-01:** Member PAT stored Fernet-encrypted on the profile; owner sees only
  `has_token: bool`. No member login account — the flow is purely "deposit your PAT
  into a profile slot."
- **L-02:** Invite is single-use (`consumed_at`) + TTL-bounded; expired/used/invalid →
  clear redeem error.
- **L-03:** Diff is **count only** (not which records). New cache column is named
  **`first_seen_at`** (GRUVAX-cache arrival time, distinct from Discogs `date_added`).
- **L-04:** The diff count is computed in the staging-swap sync and delivered on the
  `collection_changed` SSE payload.
- **L-05:** Invite-redeem posts the member PAT over plaintext HTTP on the home LAN —
  TLS is optional; document as a **runbook note**, do not build TLS termination here.
- **L-06:** `migration 0012` folds in this phase's schema changes.

### Invite link delivery + TTL
- **D-01:** Invite **TTL = 1 hour** (vs the in-person 5-min pairing code — invites are
  shared async over iMessage/email). Re-issue is cheap if it lapses.
- **D-02:** Owner obtains the link via **copy-to-clipboard** ("Copy link" button in the
  admin profile UI) and pastes it into whatever app they choose. No native Web Share
  API, no QR in this phase. Show the link + a TTL countdown while an invite is active.
- **D-03:** Link shape is `/redeem/:code` where `code` is an **opaque UUID** (uuid4),
  never a credential. The redeem route is **outside** the `/admin` PIN gate (public,
  member-facing).

### Redeem page UX (member-facing)
- **D-04:** On successful redeem (PAT validated against discogsography + stored), the
  initial sync **auto-starts** — mirrors the owner `connect` flow which kicks a sync.
  Member sees a terminal "Connected — importing your collection…" state; their job is
  done. Owner/kiosk see records arrive live via `collection_changed`.
- **D-05 (builder discretion, captured):** The redeem page shows **which profile** is
  being connected (the profile's `display_name`), a link to where the member finds
  their Discogs PAT (`https://www.discogs.com/settings/developers`), and a
  password-type PAT input. Success state is terminal ("you can close this").

### "N new records" semantics + placement
- **D-06:** "N new" = **arrivals counted via `first_seen_at`** (rows whose `first_seen_at`
  landed in this sync). Removals/sales do NOT subtract; the count is always ≥ 0. This
  matches the literal "new records" wording. (NOT a net `new_count − old_count` delta.)
- **D-07:** The **first-ever sync** for a freshly-connected profile reads as an
  **initial import** ("Imported N records"), not "N new since last sync" — there is no
  prior sync to diff against. Subsequent syncs show the true arrivals count. Implies the
  `collection_changed` payload (or sync result) needs an `is_initial_import` signal.
- **D-08:** The indicator **persists until the next sync** (on the admin diagnostics
  card + the kiosk), derived statelessly from the last sync's stored count. No transient
  toast-only behavior, no per-user dismiss state to track.

### Invite lifecycle + edge cases
- **D-09:** **One active invite per profile** — generating a new invite immediately
  voids any prior unredeemed code (mark it consumed/expired). Avoids "which link did I
  send?" ambiguity.
- **D-10:** Redeeming onto a profile that **already has a token replaces/rotates** it
  (validate → overwrite the encrypted PAT, clear `app_token_revoked`, re-sync).
  Supports the real "my Discogs token changed" case; safe because only the owner can
  mint a single-use, TTL-bounded invite.
- **D-11 (builder discretion, captured):** Redeem error copy for expired/used/invalid
  uses the **Nordic Grid plain-language voice** (no technical jargon). When a profile is
  deleted, its outstanding invite is invalidated (FK cascade or explicit cleanup).

### Claude's Discretion
- Invite-code abuse posture on the **public** redeem endpoint: the endpoint validates
  member PATs against discogsography, so a light guard (per-code attempt cap and/or
  per-IP throttle) is worth designing — flagged for the researcher/security pass, not a
  user decision.
- `has_token` derivation: from `app_token_encrypted IS NOT NULL AND NOT app_token_revoked`
  (no redundant stored column) — see code context.
- Exact admin UI placement of the "Copy invite link" affordance (ProfileDrawer PENDING
  state vs a per-row action) — a UI-phase/build detail.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — **AUTH-02** (invite/redeem PAT flow) and **API-04**
  ("N new records" count); plus the locked "Open decisions" rows for Phase 7
  (TLS-optional runbook note; `first_seen_at` naming; fake-discogsography `limit=1`
  validation support).
- `.planning/ROADMAP.md` § "Phase 7: Member Self-Connect + Collection Diff" — goal,
  success criteria, dependency on Phase 6 SSE-bus correctness.
- `.planning/PROJECT.md` — core value, constraints, security posture.

### Prior phase security/decisions to honor
- `.planning/phases/06-safe-boundaries-live-device-lifecycle/06-SECURITY.md` — the
  per-profile bus + scoped-write threat model this phase builds on (`collection_changed`
  fan-out must stay per-profile).

No external ADRs — design decisions are captured in `<decisions>` above.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **PAT crypto** — `src/gruvax/sync/pat_crypto.py:46-101` (`encrypt_pat()` / `decrypt_pat()`,
  lazy Fernet). Reuse verbatim for invite-redeem PAT storage.
- **PAT validation** — `src/gruvax/discogsography/client.py:221-229` `fetch_user_id()`
  (GET collection `limit=1`, returns `user_id`); used by `_run_test_sync()`
  (`src/gruvax/api/admin/profiles.py:145-158`). Use to validate the member's PAT at
  redeem time. The `fake-discogsography` fixture already supports the `limit=1` call
  (`src/gruvax/_internal/fake_discogsography.py:58-118`) — REQUIREMENTS confirm-item is
  satisfied.
- **Owner connect flow** — `src/gruvax/api/admin/profiles.py:430-522`
  (`POST /profiles/{id}/connect`: validate → encrypt → store → kick sync). The redeem
  endpoint is a member-facing mirror of this (auto-sync per D-04).
- **Single-use TTL token pattern** — `pairing_codes`
  (`migrations/versions/0011_devices_and_pairing_codes.py:79-141`) and the atomic
  first-wins consume `UPDATE ... WHERE consumed_at IS NULL AND expires_at > NOW()
  RETURNING ...` (`src/gruvax/api/admin/devices.py:80-87`). Direct analog for
  `profile_invite_codes` (swap CHAR(4) → uuid, drop the device-fingerprint binding).

### Established Patterns
- **Profile status** — `_profile_status(row)` and the `has_token` exposure live in
  `src/gruvax/api/admin/profiles.py:87-116, 183-275`; today responses expose
  `app_token_revoked`. Derive `has_token` here; frontend `AdminProfile`
  (`frontend/src/api/types.ts`) gains `has_token`.
- **Staging-swap sync** — `src/gruvax/sync/profile_sync.py`: `_ingest_into_staging()`
  (244-275, returns `row_count`), `_swap_inside_tx()` (281-315, DELETE old + INSERT
  staging + UPDATE profiles). The **arrivals count** (D-06) is computed inside this
  transaction; `profile_collection.synced_at` already exists (migration 0009:114-132) so
  `first_seen_at` sits beside it.
- **SSE publish** — `src/gruvax/sync/profile_sync.py:354-356` publishes
  `collection_changed {"profile_id": ...}` on the per-profile bus
  (`src/gruvax/events/bus.py:18-24`); extend with `new_record_count` (+ `is_initial_import`
  per D-07). SSE stream: `src/gruvax/api/events.py:39-87`.

### Integration Points
- **New migration 0012** (head is 0011): create `gruvax.profile_invite_codes`
  (code uuid PK, `profile_id` FK, `expires_at`, `consumed_at`, `created_at`; index on
  `expires_at`) AND `ALTER TABLE gruvax.profile_collection ADD COLUMN first_seen_at
  TIMESTAMPTZ` (nullable for backfill, set on staging insert going forward).
- **New endpoints:** owner-side `POST /profiles/{id}/invite` (generate, voids prior per
  D-09) → returns `{code/url, expires_at}`; member-side **public** `GET` (validate +
  show target profile) and `POST /redeem/{code}` (or `/api/invite-codes/{code}/redeem`)
  with `{pat}` body → validate, store/rotate (D-10), auto-sync (D-04).
- **Frontend:** new member route `/redeem/:code` OUTSIDE `/admin`
  (`frontend/src/App.tsx`); "Copy invite link" affordance in
  `frontend/src/routes/admin/ProfileDrawer.tsx` / `ProfilesManager.tsx`; "N new records"
  indicator on the admin diagnostics card + kiosk (kiosk currently ignores
  `collection_changed` — plumb it).

### Kiosk consumer caveat
- The kiosk SSE consumer handles several events but does **not** yet render
  `collection_changed` to the UI — API-04's kiosk indicator requires wiring it in
  (`frontend/src/routes/kiosk/KioskView.tsx`).
</code_context>

<specifics>
## Specific Ideas

- Redeem page should guide the member to `https://www.discogs.com/settings/developers`
  to find their PAT.
- Invite link is plain copy-paste so it works from both the kiosk (Chromium) and the
  mobile admin — no platform share-sheet dependency.
</specifics>

<deferred>
## Deferred Ideas

- **QR for invite/redeem** — considered for link delivery; deferred. The QR library
  arrives with DEV-04 (QR pairing) in Phase 8; revisit invite-QR then if desired.
- **Native Web Share API** for the invite link — deferred (Chromium/kiosk flakiness;
  copy-to-clipboard covers it).
- **Set-level "which records changed" diff** — explicitly out of scope per API-04
  (count only).

None of the above belong in Phase 7.
</deferred>

---

*Phase: 7-member-self-connect-collection-diff*
*Context gathered: 2026-05-31*

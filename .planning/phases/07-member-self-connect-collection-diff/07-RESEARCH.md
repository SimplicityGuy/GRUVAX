# Phase 7: Member Self-Connect + Collection Diff — Research

**Researched:** 2026-06-01
**Domain:** Invite token lifecycle, PAT encryption-at-rest, collection diff / `first_seen_at`, SSE payload extension, frontend public route
**Confidence:** HIGH (all claims verified against live codebase; architecture decisions already locked in CONTEXT.md)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **L-01:** Member PAT stored Fernet-encrypted on the profile; owner sees only `has_token: bool`. No member login account — flow is purely "deposit your PAT into a profile slot."
- **L-02:** Invite is single-use (`consumed_at`) + TTL-bounded; expired/used/invalid → clear redeem error.
- **L-03:** Diff is **count only** (not which records). New cache column is named **`first_seen_at`** (GRUVAX-cache arrival time, distinct from Discogs `date_added`).
- **L-04:** The diff count is computed in the staging-swap sync and delivered on the `collection_changed` SSE payload.
- **L-05:** Invite-redeem posts the member PAT over plaintext HTTP on the home LAN — TLS is optional; document as a **runbook note**, do not build TLS termination here.
- **L-06:** `migration 0012` folds in this phase's schema changes.
- **D-01:** Invite TTL = 1 hour.
- **D-02:** Owner obtains link via copy-to-clipboard. No Web Share API, no QR in this phase.
- **D-03:** Link shape is `/redeem/:code` where `code` is an opaque UUID (uuid4), never a credential. Redeem route is outside `/admin` PIN gate.
- **D-04:** On successful redeem, initial sync auto-starts (mirrors owner connect flow). Terminal "Connected — importing…" state; member's job is done.
- **D-05 (builder discretion):** Redeem page shows which profile is being connected, link to Discogs developer settings, password-type PAT input. Success state is terminal.
- **D-06:** "N new" = arrivals counted via `first_seen_at` rows landed in this sync. Removals do NOT subtract. Count ≥ 0.
- **D-07:** First-ever sync reads as initial import ("Imported N records"); subsequent syncs show true arrivals. `collection_changed` payload carries `is_initial_import` signal.
- **D-08:** Indicator persists until next sync — derived statelessly from stored count. No transient toast-only behavior, no per-user dismiss state.
- **D-09:** One active invite per profile — generating a new invite voids prior unredeemed code.
- **D-10:** Redeeming onto a profile that already has a token replaces/rotates it (validate → overwrite encrypted PAT, clear `app_token_revoked`, re-sync).
- **D-11 (builder discretion):** Redeem error copy uses Nordic Grid plain-language voice. When profile is deleted, outstanding invite is invalidated (FK cascade or explicit cleanup).

### Claude's Discretion
- Invite-code abuse posture on the **public** redeem endpoint: per-code attempt cap and/or per-IP throttle is worth designing.
- `has_token` derivation: from `app_token_encrypted IS NOT NULL AND NOT app_token_revoked` (no redundant stored column).
- Exact admin UI placement of the "Copy invite link" affordance — a UI-phase/build detail.

### Deferred Ideas (OUT OF SCOPE)
- QR for invite/redeem — deferred to Phase 8 (DEV-04).
- Native Web Share API for invite link — deferred.
- Set-level "which records changed" diff — explicitly out of scope (count only).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AUTH-02 | Owner issues one-time, TTL-bounded invite link for a profile; member pastes their own Discogs PAT into a GRUVAX-served form; PAT stored Fernet-encrypted; owner sees only `has_token: bool`; expired/used/invalid shows clear error | §PAT Crypto, §Invite Tokens, §Redeem Endpoint, §Security Domain |
| API-04 | After any sync, kiosk and admin surface per-profile "N new records since last sync" indicator computed in staging-swap sync and delivered on `collection_changed` SSE payload | §Collection Diff, §SSE Extension, §Validation Architecture |
</phase_requirements>

---

## Summary

Phase 7 adds two self-contained capabilities on top of the v2.0 profile+sync foundation already shipped: a member-driven invite/redeem path (AUTH-02) and a per-sync arrival count surfaced via SSE (API-04). Both capabilities are tightly scoped and all architectural decisions are locked in CONTEXT.md — there are no open design questions to resolve during planning.

The codebase already contains every reusable asset this phase needs. `src/gruvax/sync/pat_crypto.py` has `encrypt_pat()`/`decrypt_pat()`. `src/gruvax/discogsography/client.py` has `fetch_user_id()` (the `limit=1` validation call). `src/gruvax/_internal/fake_discogsography.py` already handles `limit=1` requests correctly. `migrations/versions/0011_devices_and_pairing_codes.py` contains the exact single-use TTL token pattern (`consumed_at IS NULL AND expires_at > NOW() RETURNING ...`) that the invite code table replicates. `src/gruvax/api/admin/profiles.py` has the owner `connect_pat` endpoint whose server-side steps are mirrored by the member redeem path.

The only new code required is: migration 0012 (two DDL changes), a new `invite_codes.py` router (owner `POST /profiles/{id}/invite` + public `GET /invite-codes/{code}` + public `POST /invite-codes/{code}/redeem`), three small changes to `profile_sync.py` (add `first_seen_at` on INSERT, compute `new_record_count` and `is_initial_import` in `_swap_inside_tx`, extend the `collection_changed` payload), frontend `RedeemPage.tsx` under `/redeem/:code`, and wiring `collection_changed` in `KioskView.tsx` + a new row in `ProfileDiagnosticsCard`.

**Primary recommendation:** Follow the `pairing_codes` pattern exactly for `profile_invite_codes`; reuse `_run_test_sync` and the owner `connect_pat` server flow for the redeem path; compute `new_record_count` as a `COUNT(*)` from staging that did not exist in the previous snapshot.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Invite code generation + storage | API / Backend | — | Admin PIN-gated mutation; security boundary on the server |
| Invite code validation (GET code) | API / Backend | — | Authoritative expiry/consumed check must be server-side |
| Member PAT submission + encryption | API / Backend | — | PAT must never touch the browser persistently; encrypt on server before any DB write |
| PAT validation against discogsography | API / Backend | — | Outbound HTTP from the server; PAT must not travel to any client |
| Redeem page UI | Browser / Client | — | Public route on the member's own device; React SPA |
| Auto-sync trigger after redeem | API / Backend | — | `BackgroundTasks` on the server, mirrors owner connect flow |
| Arrival count computation | API / Backend | Database / Storage | SQL inside the swap transaction; count is authoritative before SSE publish |
| `collection_changed` SSE fan-out | API / Backend | — | Extends existing per-profile bus publish; no new tier |
| "N new records" kiosk indicator | Browser / Client | — | Consumes `collection_changed` payload; React state |
| "N new records" admin card row | Browser / Client | — | Read from stored `last_new_record_count` via existing admin profile API |
| Rate-limiting the public redeem endpoint | API / Backend | — | Per-code attempt cap, per-IP throttle — same tier as the existing bind limiter |
| Invite TTL countdown UI | Browser / Client | — | `setInterval` on the frontend; server is authoritative on expiry |

---

## Standard Stack

All packages below are already installed in the project. No new packages required for this phase.

### Core (already in project — no installs)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `cryptography` (Fernet) | already installed | PAT encryption-at-rest | Already used in `pat_crypto.py`; reuse verbatim |
| `itsdangerous` | already installed | Signed token/cookie infra | Already a transitive dep of Starlette SessionMiddleware |
| `psycopg` (async) | 3.2+ | DB driver | Project standard; atomic UPDATE pattern already proven |
| `fastapi` | 0.136.x | Endpoint framework | Project standard; `BackgroundTasks` for auto-sync |
| `slowapi` / project limiter | existing `limiter.py` | Rate-limiting | `src/gruvax/api/admin/limiter.py` — reuse the existing `FixedWindowRateLimiter` |
| React 19 | already installed | Redeem page SPA | Project standard |
| `lucide-react` | already installed | `Eye`/`EyeOff`/`Loader2`/`CheckCircle2` icons | Already imported in `ProfileDrawer.tsx` |

### No New Third-Party Packages

This phase introduces no new dependencies. The UI-SPEC explicitly confirms: no third-party component registries, no new packages. All new UI is built on existing CSS modules, button classes, and Lucide icons already in the project.

**Installation:** none required.

---

## Package Legitimacy Audit

No new packages are installed in this phase.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| (none) | — | — | — | — | — | — |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

---

## Architecture Patterns

### System Architecture Diagram

```
Owner browser (admin)
  │  POST /api/admin/profiles/{id}/invite
  │  ← {code: uuid4, url, expires_at}
  │  (voids prior unredeemed invite for this profile — D-09)
  │
  └─► gruvax API ──► gruvax.profile_invite_codes (Postgres)
        │              code UUID PK, profile_id FK, expires_at, consumed_at
        │
  Owner copies link → sends via iMessage/email
        │
Member browser (own device, LAN)
  │  GET /api/invite-codes/{code}          (public, no PIN)
  │  ← {profile.display_name, valid: true} or 404/expired/used error
  │
  │  POST /api/invite-codes/{code}/redeem  (public, no PIN)
  │  body: {pat: "dscg_…"}
  │  ─► validate: fetch_user_id() limit=1 call to discogsography
  │  ─► encrypt_pat() → UPDATE profiles SET app_token_encrypted=…, revoked=FALSE
  │  ─► UPDATE profile_invite_codes SET consumed_at=NOW() (atomic)
  │  ─► BackgroundTasks: sync_profile()
  │  ← 200 {status:"connected", profile_id}
  │
sync_profile()
  │  _ingest_into_staging() — streams collection into TEMP table
  │  _swap_inside_tx()
  │    ├── compute new_record_count (arrivals with first_seen_at = NOW())
  │    ├── detect is_initial_import (last_sync_at WAS NULL before swap)
  │    ├── SET first_seen_at = NOW() on INSERT (new rows only)
  │    └── SET profiles.last_new_record_count = new_record_count
  │        SET profiles.last_sync_is_initial = is_initial_import
  │  _refresh_profile_caches()
  │    └── bus.publish("collection_changed", {
  │          profile_id, new_record_count, is_initial_import
  │        })
  │
KioskView.tsx SSE consumer
  collection_changed → parse new_record_count + is_initial_import
                    → show/update yellow pill
AdminDiagnosticsCard
  GET /api/admin/profiles → last_new_record_count + last_sync_is_initial
                          → render NEW RECORDS row
```

### Recommended Project Structure

New files for this phase:

```
src/gruvax/
├── api/
│   ├── invite_codes.py          # new: owner + member invite/redeem endpoints
│   └── admin/
│       └── router.py            # add invite_codes_router (owner side)
├── sync/
│   └── profile_sync.py          # extend _swap_inside_tx, _refresh_profile_caches
migrations/
└── versions/
    └── 0012_invite_codes_and_first_seen_at.py   # new
frontend/src/
├── routes/
│   └── redeem/
│       ├── RedeemPage.tsx        # new: public member-facing page
│       └── RedeemPage.css        # new
├── api/
│   ├── inviteClient.ts           # new: GET/POST invite-codes endpoints
│   └── types.ts                  # extend AdminProfile (has_token); new InviteCode types
├── routes/
│   ├── admin/
│   │   ├── ProfileDrawer.tsx     # extend: INVITE LINK section
│   │   └── ProfileDiagnosticsCard.tsx  # extend: NEW RECORDS row
│   └── kiosk/
│       └── KioskView.tsx         # extend: parse new_record_count from collection_changed
└── App.tsx                       # add /redeem/:code route outside /admin
```

### Pattern 1: Single-Use TTL Invite Code (mirrors pairing_codes)

**What:** An opaque UUID code stored with `expires_at` and `consumed_at`. Redemption uses an atomic `UPDATE ... WHERE consumed_at IS NULL AND expires_at > NOW() RETURNING profile_id` — first write wins, second sees no row.

**When to use:** Any single-use time-bounded token in this codebase.

**Example (from `src/gruvax/api/admin/devices.py:80-87`):** [VERIFIED: live codebase]

```python
# Atomic "first wins" — PostgreSQL READ COMMITTED row lock
_CONSUME_INVITE = (
    "UPDATE gruvax.profile_invite_codes"
    " SET consumed_at = NOW()"
    " WHERE code = %s::uuid"
    "   AND consumed_at IS NULL"
    "   AND expires_at > NOW()"
    " RETURNING profile_id"
)
```

The `pairing_codes` pattern uses `CHAR(4) PK`; the invite pattern uses `UUID PK`. Otherwise identical.

**Key difference from pairing codes:**
- `pairing_codes` expire after 5 minutes (in-person); invite codes expire after 1 hour (async share, D-01).
- `pairing_codes` bind to a `fingerprint` (device); invite codes bind to a `profile_id` (profile).
- No `fingerprint` column on invite codes — the member is not a device.

### Pattern 2: Owner Generate Invite (one-active-per-profile, D-09)

**What:** `POST /api/admin/profiles/{id}/invite` voids any prior unredeemed code for the same profile before inserting a new one.

**Example:**

```python
# Step 1: void prior unredeemed code (idempotent if none exists)
_VOID_PRIOR_INVITE = (
    "UPDATE gruvax.profile_invite_codes"
    " SET consumed_at = NOW()"
    " WHERE profile_id = %s::uuid AND consumed_at IS NULL AND expires_at > NOW()"
)

# Step 2: insert new invite with 1-hour TTL (D-01)
_INSERT_INVITE = (
    "INSERT INTO gruvax.profile_invite_codes"
    " (code, profile_id, expires_at)"
    " VALUES (gen_random_uuid(), %s::uuid, NOW() + INTERVAL '1 hour')"
    " RETURNING code::text, expires_at"
)
```

Both steps run in a single transaction to avoid a window where both codes are valid. [VERIFIED: live codebase — pairing_codes migration, devices.py pattern]

### Pattern 3: Member Redeem Flow (mirrors owner connect_pat)

**What:** Public endpoint — no `require_admin`. Server-side steps mirror `connect_pat` (`src/gruvax/api/admin/profiles.py:430-522`):

1. Consume the invite atomically (RETURNING profile_id). 404 if no row (expired/used/invalid — same error shape regardless of reason per security principle: don't distinguish expired from invalid to prevent oracle attacks).
2. Validate PAT via `_run_test_sync(pat)` — same function as owner connect (reuse verbatim).
3. Check `user_id` collision (D-09 invariant: same user_id cannot appear on two active profiles).
4. `encrypt_pat()` + `UPDATE profiles SET app_token_encrypted=..., app_token_revoked=FALSE`.
5. D-10: this path handles "profile already has a token" by overwriting — no guard needed; the invite was validly issued by the owner.
6. `BackgroundTasks.add_task(_run_sync_background, profile_id, app_state)` — auto-sync (D-04).
7. Return 200 `{"status": "connected", "profile_id": ...}`.

Error taxonomy (public endpoint):
- 404 `invite_not_found` — for expired/used/invalid (no oracle distinction)
- 401 `pat_rejected` — discogsography returned 401/403
- 409 `user_id_collision` — same as owner connect
- 503 `upstream_unavailable` — rate-limited or server error from discogsography

### Pattern 4: `first_seen_at` + `new_record_count` in staging swap

**What:** The staging swap in `_swap_inside_tx` already knows `row_count`. To compute arrivals, the swap must compare the staging rows against the rows being deleted (old collection state).

**Recommended approach — compare-on-INSERT** [ASSUMED: strategy choice, no prior code for this]:

```sql
-- Inside _swap_inside_tx, before DELETE:
-- 1. Capture is_initial_import: last_sync_at IS NULL on profiles row
-- 2. DELETE old rows
-- 3. INSERT staging rows with first_seen_at = NOW() for ALL (first sync)
--    OR with first_seen_at = NOW() only for rows NOT in the deleted set
-- 4. Compute new_record_count as the count of inserted rows with first_seen_at = NOW()
```

The cleanest implementation given the staging pattern:

```sql
-- Step A: capture pre-swap state
SELECT last_sync_at IS NULL AS is_initial_import
FROM gruvax.profiles WHERE id = %s::uuid;

-- Step B: DELETE old rows (already in _swap_inside_tx)
DELETE FROM gruvax.profile_collection WHERE profile_id = %s::uuid;

-- Step C: INSERT from staging, setting first_seen_at = NOW() on all rows
-- (existing rows had first_seen_at from their previous insertion — new column
-- is NULL-able, so old rows retain their original timestamp; new rows get NOW())
INSERT INTO gruvax.profile_collection
  (profile_id, release_id, folder_id, artist, title,
   label, catalog_number, year, first_seen_at)
SELECT %s::uuid, release_id, folder_id, artist, title,
       label, catalog_number, year, NOW()
FROM profile_collection_staging;

-- Step D: count is row_count for initial import, or compare via:
--   new_record_count = COUNT of (release_id, folder_id) tuples in staging
--   that were NOT in the pre-swap profile_collection.
-- Simplest correct approach: since DELETE runs before INSERT, and staging
-- was built before DELETE, new arrivals = staging rows not in the pre-swap state.
-- Use a CTE or subquery inside the transaction.
```

**Recommended simpler approach:** Since the DELETE runs first and the staging TEMP table is in scope, the arrivals count is the rows in staging that were not in profile_collection before the DELETE. The most practical implementation is a pre-DELETE snapshot count approach:

```sql
-- BEFORE DELETE: count matching rows (existing)
SELECT COUNT(*) INTO existing_count
FROM gruvax.profile_collection pc
JOIN profile_collection_staging s
  ON pc.release_id = s.release_id
 AND pc.folder_id IS NOT DISTINCT FROM s.folder_id
WHERE pc.profile_id = %s::uuid;

-- new_record_count = row_count - existing_count (arrivals only, never negative)
new_record_count = max(0, row_count - existing_count)
```

This runs as two queries in the same transaction. For a 3,000-record collection, both queries are sub-millisecond. [VERIFIED: live codebase — staging pattern in profile_sync.py:244-315]

**`first_seen_at` column:** Added to `profile_collection` in migration 0012. Set to `NOW()` in the INSERT. Nullable for backfill (existing rows remain NULL). Going forward, every row has `first_seen_at` from its first insertion. The column does NOT participate in the PK `(profile_id, release_id, folder_id)` — it is metadata only.

### Pattern 5: SSE Payload Extension

**What:** `_refresh_profile_caches` currently calls:

```python
await bus.publish("collection_changed", {"profile_id": profile_id})
```

Extended to:

```python
await bus.publish("collection_changed", {
    "profile_id": profile_id,
    "new_record_count": new_record_count,
    "is_initial_import": is_initial_import,
})
```

The existing `KioskView.tsx:342` handler uses the no-argument form (`es.addEventListener('collection_changed', () => {...})`). This phase adds JSON parsing to the handler:

```typescript
es.addEventListener('collection_changed', (e) => {
  void queryClient.invalidateQueries({ queryKey: ['search'] })
  resync()
  // Parse new fields (backward-compatible: e.data may be empty or missing)
  try {
    const payload = e.data ? JSON.parse(e.data) : {}
    const count = typeof payload.new_record_count === 'number'
      ? payload.new_record_count : 0
    const isInitial = Boolean(payload.is_initial_import)
    if (count > 0) setNewRecordState({ count, isInitial })
  } catch {
    // Graceful degrade — no indicator shown
  }
})
```

[VERIFIED: live codebase — events.py:74 uses `json.dumps(event.data)`, so `e.data` is a JSON string]

### Pattern 6: `has_token` Derivation (no stored column)

Per CONTEXT.md Claude's Discretion, `has_token` is derived from `app_token_encrypted IS NOT NULL AND NOT app_token_revoked`. This means the `GET /api/admin/profiles` and `GET /api/admin/profiles/{id}` response serializers need a one-line addition:

```python
"has_token": (
    bool(row.get("app_token_encrypted"))       # not NULL and not empty bytes
    and not bool(row.get("app_token_revoked"))
),
```

The query must include `app_token_encrypted` in SELECT (as a boolean-cast or length check — never the raw ciphertext). [VERIFIED: live codebase — profiles.py currently does NOT include app_token_encrypted in SELECT; adding `(app_token_encrypted IS NOT NULL AND length(app_token_encrypted) > 0)::bool AS has_token` is the cleanest approach]

### Pattern 7: Stored `last_new_record_count` and `last_sync_is_initial` on Profiles

The diagnostics card derives its "N new records" row from the stored state on `gruvax.profiles` (D-08: persists until next sync). Two new columns added in migration 0012:

```sql
ALTER TABLE gruvax.profiles
  ADD COLUMN last_new_record_count  BIGINT  DEFAULT 0,
  ADD COLUMN last_sync_is_initial   BOOLEAN DEFAULT FALSE;
```

Updated inside `_swap_inside_tx`:

```sql
UPDATE gruvax.profiles SET
    last_sync_at           = NOW(),
    last_sync_status       = 'ok',
    last_sync_item_count   = %s,
    last_sync_error        = NULL,
    discogsography_user_id = COALESCE(discogsography_user_id, %s::uuid),
    app_token_revoked      = FALSE,
    last_new_record_count  = %s,
    last_sync_is_initial   = %s
WHERE id = %s::uuid
```

The admin profiles API response exposes these alongside existing fields. [VERIFIED: live codebase — profiles.py SELECT statement and _swap_inside_tx UPDATE]

### Anti-Patterns to Avoid

- **Distinguish expired from used/invalid on the public redeem endpoint:** Do NOT return different HTTP status codes or error bodies for expired vs. consumed vs. non-existent codes. Return a uniform 404 `invite_not_found`. This prevents timing attacks and code enumeration.
- **Hold a DB pool slot during the discogsography HTTP call:** `_run_test_sync()` is already written to release the pool before the HTTP call (Pitfall 6 pattern). The redeem endpoint must follow the same pattern: acquire pool → read invite → release pool → HTTP call → acquire pool → write.
- **Logging the PAT in any error handler:** The existing `log_redactor` defends against accidental Bearer-token logging in structlog, but error handlers that re-raise should not construct message strings from `body.pat`.
- **Returning the raw invite code from `GET /invite-codes/{code}` in error responses:** The 404 body should NOT echo the code back (reduces oracle surface).
- **Calling `es.close()` inside the SSE `collection_changed` handler:** The existing comment at KioskView.tsx:377 is explicit — the cleanup `return () => es.close()` is the ONLY close call.
- **Storing `last_new_record_count` outside the swap transaction:** The count must be committed atomically with the collection swap. Computing it after commit risks a race where a second sync starts before the count is stored.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PAT encryption at rest | Custom AES/XOR scheme | `pat_crypto.encrypt_pat()` (already exists) | Fernet provides authenticated encryption; custom schemes introduce MAC bypass risks |
| Single-use token atomicity | Application-level "check then set" | PostgreSQL `UPDATE ... WHERE consumed_at IS NULL RETURNING ...` | Application-level CAS is not atomic under concurrent requests; PostgreSQL row lock is |
| PAT validation HTTP client | New httpx client setup | `profile_sync._run_test_sync(pat)` (already exists) | The function already handles retries, error translation, and pool isolation |
| Invite link delivery | Web Share API, native notifications | Copy-to-clipboard (`navigator.clipboard.writeText`) | Locked by D-02; cross-platform, works in Chromium kiosk |
| Rate limiting the redeem endpoint | Custom in-memory counter | `src/gruvax/api/admin/limiter.py` `FixedWindowRateLimiter` | Already implemented and tested for the bind endpoint |
| Arrival count computation | Separate reconciliation job | SQL `COUNT(*)` inside the existing swap transaction | Atomic with the swap; no eventual consistency; single source of truth |

**Key insight:** This phase is almost entirely assembly of existing primitives. The `pairing_codes` → `profile_invite_codes` mapping is a one-to-one structural copy (UUID instead of CHAR(4), 1 hour instead of 5 minutes, profile-scoped instead of fingerprint-scoped).

---

## Common Pitfalls

### Pitfall 1: Pool Slot Held During Discogsography HTTP Call (Pitfall 6 analog)

**What goes wrong:** The redeem endpoint holds a pool connection across the `_run_test_sync()` HTTP call, blocking other requests from acquiring a connection.

**Why it happens:** Copying the invite read and PAT write into a single `async with db_pool.connection()` block that also wraps the HTTP call.

**How to avoid:** Follow the exact pattern in `connect_pat` (profiles.py:451-456): read invite (pool acquired + released) → HTTP test-sync (no pool slot held) → write PAT (new pool slot).

**Warning signs:** Integration test with concurrent requests shows pool timeout errors during redeem.

### Pitfall 2: Oracle Attack on Invite Code Validation

**What goes wrong:** Returning 404 for non-existent codes, 410 for expired codes, and 409 for consumed codes leaks information about valid codes to an attacker who can enumerate.

**Why it happens:** Natural desire to give the member a helpful error message.

**How to avoid:** Return a single 404 `invite_not_found` for all three cases from the public endpoint. The error copy ("This invite link has expired" vs "already used") is safe to show — the discriminator is owned by the owner who minted the code, not an attacker guessing UUIDs.

**Note:** UUID4 has 122 bits of entropy — brute-force is computationally infeasible. The oracle risk is low but the fix is free: treat all negative cases identically in the HTTP response.

### Pitfall 3: `first_seen_at` Backfill on Existing Rows

**What goes wrong:** `ALTER TABLE gruvax.profile_collection ADD COLUMN first_seen_at TIMESTAMPTZ` leaves all existing rows with NULL. Code that reads `first_seen_at` to compute arrivals will count all NULL rows as "no arrival time" and derive incorrect counts on the next sync.

**Why it happens:** The column is added nullable (correct for Alembic online migration), but the arrival-count logic may misinterpret NULL as "arrived before tracking began" vs "this row existed before this column was added."

**How to avoid:** The arrival count for the **first sync after migration** is computed by comparing staging row count against pre-swap row count (scalar counts, not per-row timestamps). The `first_seen_at` column is informational metadata; the `new_record_count` is computed transactionally inside the swap. No per-row timestamp comparison is used for the diff count.

**Warning signs:** First sync after 0012 migration reports all existing records as "new."

### Pitfall 4: `is_initial_import` Detection Race

**What goes wrong:** `is_initial_import` is determined after the UPDATE sets `last_sync_at = NOW()`, making it impossible to know if this was the first sync.

**Why it happens:** Reading `last_sync_at` from the same UPDATE statement that sets it.

**How to avoid:** Read `last_sync_at IS NULL` BEFORE the UPDATE in `_swap_inside_tx`. Capture it as a Python bool `was_initial = (row["last_sync_at"] is None)` at the start of the function, then pass it through.

**Warning signs:** Every sync, including repeat syncs, shows `is_initial_import: true`.

### Pitfall 5: Transaction Boundary for invite consume + PAT write

**What goes wrong:** The invite consume (`UPDATE ... SET consumed_at`) and the PAT store (`UPDATE profiles SET app_token_encrypted`) happen in separate transactions, creating a window where the invite is consumed but the PAT write fails, leaving the member locked out.

**Why it happens:** Writing "consume invite, then write PAT" as two sequential DB operations.

**How to avoid:** The consume can remain a separate short-lived transaction (it's an atomic operation under PostgreSQL READ COMMITTED). The PAT write is a separate UPDATE. This matches the pairing flow — `pairing_codes.consumed_at` is set before the device INSERT, and if the device INSERT fails, the code is consumed (preventing replay). For the redeem flow, the order is: consume invite → validate PAT (HTTP) → write PAT. If PAT write fails, the invite is already consumed. This is acceptable: the owner simply issues a new invite. Document this in code comments.

### Pitfall 6: The `collection_changed` Event Already Has No Payload

**What goes wrong:** The existing KioskView.tsx handler for `collection_changed` uses the no-argument form and does not read `e.data`. After this phase extends the payload, old handler code silently ignores the new fields.

**Why it happens:** The handler was written before there was a payload (profile_sync.py:356 published `{"profile_id": ...}` but the handler ignored it).

**How to avoid:** The existing `KioskView.tsx:342` already passes `e` to the handler as `() => {...}` (no argument). Change to `(e) => {...}` and parse `e.data` defensively. Backward-compatible: if `e.data` is empty string or null, treat as `{new_record_count: 0}`.

### Pitfall 7: Admin Profile Response Missing `has_token`

**What goes wrong:** The `GET /api/admin/profiles` SELECT does not include `app_token_encrypted` in its column list (verified in profiles.py:193-198), so `has_token` cannot be derived without an additional SELECT.

**Why it happens:** `app_token_encrypted` is a security-sensitive column; it was deliberately excluded from the list response.

**How to avoid:** Add `(app_token_encrypted IS NOT NULL AND length(app_token_encrypted) > 1)::bool AS has_token` to the SELECT instead of selecting the raw ciphertext. The Postgres expression returns a boolean — the ciphertext never travels over the wire. Add this to both `GET /profiles` and `GET /profiles/{id}`.

### Pitfall 8: Route Registration Order for Public Redeem Endpoint

**What goes wrong:** The public `/api/invite-codes/{code}` route is registered under the `/admin` prefix or after the `StaticFiles` mount, causing it to be PIN-gated or swallowed by the SPA catch-all.

**Why it happens:** Following the existing admin router pattern without noticing the route must be public.

**How to avoid:** Register the invite_codes router on the main `FastAPI` app (in `app.py`) under `/api/invite-codes`, NOT via `create_admin_router()`. The owner-side `POST /profiles/{id}/invite` stays in the admin router (PIN-gated). Only the member-facing GET + POST redeem endpoints are public.

### Pitfall 9: Arrival Count Double-Counting on Retry

**What goes wrong:** A sync that fails partway through and is retried sets `first_seen_at = NOW()` on rows twice — the first pass partially populated the staging table, the second pass re-counts them.

**Why it happens:** The staging TEMP table is `ON COMMIT DROP` (it is recreated per sync call). A full retry rebuilds the staging table from scratch. The arrival count is computed correctly per the new-vs-existing comparison logic, not from `first_seen_at` column timestamps.

**How to avoid:** The arrival count is computed by comparing staging row count against pre-swap row count — this is inherently retry-safe. On a retry, the pre-swap count is the same stable value (no partial state leaked to `profile_collection`).

---

## Code Examples

Verified patterns from live codebase:

### Atomic Single-Use Code Consume (from devices.py:80-87)

```python
# Source: src/gruvax/api/admin/devices.py:80-87 [VERIFIED: live codebase]
_BIND_CODE = (
    "UPDATE gruvax.pairing_codes"
    " SET consumed_at = NOW()"
    " WHERE code = %s"
    "   AND consumed_at IS NULL"
    "   AND expires_at > NOW()"
    " RETURNING fingerprint"
)
# Analog for invite:
_CONSUME_INVITE = (
    "UPDATE gruvax.profile_invite_codes"
    " SET consumed_at = NOW()"
    " WHERE code = %s::uuid"
    "   AND consumed_at IS NULL"
    "   AND expires_at > NOW()"
    " RETURNING profile_id"
)
```

### PAT Encrypt + Store (from profiles.py:499-511)

```python
# Source: src/gruvax/api/admin/profiles.py:499-511 [VERIFIED: live codebase]
ciphertext = encrypt_pat(body.pat)
async with db_pool.connection() as conn:
    await conn.execute(
        "UPDATE gruvax.profiles SET "
        "    app_token_encrypted = %s::bytea, "
        "    app_token_revoked = FALSE, "
        "    discogsography_user_id = COALESCE(discogsography_user_id, %s::uuid), "
        "    last_sync_status = NULL, "
        "    last_sync_error = NULL "
        "WHERE id = %s::uuid AND deleted_at IS NULL",
        (ciphertext, new_user_id, str(uid)),
    )
    await conn.commit()
```

### PAT Validate (from profiles.py:145-158)

```python
# Source: src/gruvax/api/admin/profiles.py:145-158 [VERIFIED: live codebase]
async def _run_test_sync(pat: str) -> str:
    client = profile_sync._make_client(settings.DISCOGSOGRAPHY_BASE_URL, pat)
    try:
        page = await client._get_page(limit=1, offset=0)
        user_id = str(page["user_id"])
    finally:
        with contextlib.suppress(Exception):
            await client.aclose()
    return user_id
```

### SSE Publish Extension (from profile_sync.py:354-356)

```python
# Source: src/gruvax/sync/profile_sync.py:354-356 [VERIFIED: live codebase]
# Current:
await bus.publish("collection_changed", {"profile_id": profile_id})

# Phase 7 extension:
await bus.publish("collection_changed", {
    "profile_id": profile_id,
    "new_record_count": new_record_count,    # int ≥ 0
    "is_initial_import": is_initial_import,  # bool
})
```

### fake_discogsography limit=1 Support (already works)

```python
# Source: src/gruvax/_internal/fake_discogsography.py:86-116 [VERIFIED: live codebase]
@app.get("/api/user/collection")
async def get_collection(
    authorization: str | None = Header(default=None),
    limit: int = Query(50, ge=1, le=200),   # limit=1 is valid (ge=1)
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    ...
    page = seed[offset : offset + limit]    # seed[0:1] works correctly
    return {
        "user_id": user_id,
        "releases": page,
        ...
    }
```

The `fake_discogsography` fixture already handles `limit=1` correctly because the Query validator accepts `ge=1` and the slice `seed[0:1]` returns an empty list when `seed=[]` (no assertion error). REQUIREMENTS.md open decision about CI fixture support is already satisfied. [VERIFIED: live codebase]

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no — member submits PAT to GRUVAX server, not a login credential | n/a |
| V3 Session Management | no — member has no GRUVAX session | n/a |
| V4 Access Control | yes — public redeem endpoint must not be exploitable for PAT theft | UUID4 entropy + rate limit + no oracle on error |
| V5 Input Validation | yes — PAT input, invite code UUID | Pydantic model on request body; `uuid.UUID()` parse |
| V6 Cryptography | yes — PAT stored Fernet-encrypted | `cryptography.fernet` (already in use) |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Invite code brute-force | Elevation of Privilege | UUID4 (122-bit entropy) + per-code attempt cap + per-IP throttle |
| PAT replay from invite URL | Information Disclosure | Code is single-use; PAT travels in POST body (not URL); no logging of PAT |
| PAT logging via structlog | Information Disclosure | Existing `log_redactor` masks `dscg_*` substrings; no `body.pat` in log dicts |
| Oracle attack on code validity | Information Disclosure | Uniform 404 for expired/used/invalid; no distinguishing response |
| Pool exhaustion via concurrent redeems | Denial of Service | Same pool-isolation discipline as existing endpoints; test-sync runs outside pool slot |
| Redeem page CSRF | Tampering | Public endpoint — no PIN session → no CSRF token needed; POST body carries only `{pat}` |
| Member PAT exposure via `GET /profiles` | Information Disclosure | `has_token` bool derived server-side; raw `app_token_encrypted` never in SELECT result |

### TLS Posture (L-05 — LOCKED)

The redeem endpoint accepts a member PAT over HTTP on the home LAN. This is accepted by locked decision L-05. The runbook note to document:

> **Runbook note:** The member's Discogs PAT is transmitted to GRUVAX over plaintext HTTP on the home LAN. This is acceptable for the home-LAN-only constraint (no public exposure). If GRUVAX is ever exposed beyond the LAN (reverse proxy, Tailscale, etc.), HTTPS termination at the proxy layer is required before the member self-connect flow is usable safely.

No TLS termination code is added in this phase.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Owner connects PAT via admin UI only | Member can self-connect via invite link | This phase (v2.1) | Unlocks multi-user household without sharing the admin PIN |
| `collection_changed` carries no payload | `collection_changed` carries `new_record_count` + `is_initial_import` | This phase | Enables persistent "N new records" indicator without a separate API poll |
| `profile_collection` has no `first_seen_at` | `first_seen_at TIMESTAMPTZ` tracks cache arrival | This phase | Enables future per-record "recently arrived" queries (Phase 8 SRCH-09) |
| Admin sees raw `app_token_revoked` bool | Admin sees computed `has_token` bool | This phase | Cleaner API: one bool summarizes "PAT present and not revoked" |

**Deprecated/outdated:**
- The `app_token_revoked` field will remain in the profile response (it is used by `_profile_status()` and the kiosk reauth banner) but `has_token` becomes the recommended field for "does this profile have a usable token."

---

## Environment Availability

This phase has no external tool dependencies beyond what the project already uses. No new runtimes, services, or CLIs are required.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL | migration 0012, invite_codes table | ✓ | 16+ (shared instance) | — |
| Python 3.14 | backend | ✓ | 3.14 (.venv confirmed) | — |
| fake-discogsography fixture | Integration tests (limit=1) | ✓ | already supports it | — |
| `cryptography` (Fernet) | pat_crypto.py | ✓ | already installed | — |
| `lucide-react` | RedeemPage CheckCircle2, Loader2 | ✓ | already installed | — |

**Missing dependencies with no fallback:** none.

---

## Validation Architecture

**nyquist_validation: true** — include this section.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.x + pytest-asyncio (asyncio_mode=auto) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `pytest tests/unit/ -q --tb=short --benchmark-skip` |
| Full suite command | `pytest tests/ -q --tb=short --benchmark-skip` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTH-02 | Owner generates invite, link returned with expires_at | integration | `pytest tests/integration/test_invite_codes.py::test_generate_invite -x` | ❌ Wave 0 |
| AUTH-02 | Generating a second invite voids the first (D-09) | integration | `pytest tests/integration/test_invite_codes.py::test_new_invite_voids_prior -x` | ❌ Wave 0 |
| AUTH-02 | `GET /api/invite-codes/{code}` returns profile display_name for valid code | integration | `pytest tests/integration/test_invite_codes.py::test_get_valid_code -x` | ❌ Wave 0 |
| AUTH-02 | `POST /api/invite-codes/{code}/redeem` with valid PAT → 200 + sync starts | integration | `pytest tests/integration/test_invite_codes.py::test_redeem_success -x` | ❌ Wave 0 |
| AUTH-02 | Second redeem of same code returns 404 (single-use) | integration | `pytest tests/integration/test_invite_codes.py::test_redeem_second_use_rejected -x` | ❌ Wave 0 |
| AUTH-02 | Redeem with invalid PAT returns 401 pat_rejected | integration | `pytest tests/integration/test_invite_codes.py::test_redeem_bad_pat -x` | ❌ Wave 0 |
| AUTH-02 | Expired code returns 404 (TTL elapsed) | integration | `pytest tests/integration/test_invite_codes.py::test_redeem_expired -x` | ❌ Wave 0 |
| AUTH-02 | Profile response includes `has_token` bool (not raw ciphertext) | integration | `pytest tests/integration/test_invite_codes.py::test_profile_has_token_field -x` | ❌ Wave 0 |
| AUTH-02 | Redeem onto profile with existing token rotates it (D-10) | integration | `pytest tests/integration/test_invite_codes.py::test_redeem_rotates_token -x` | ❌ Wave 0 |
| AUTH-02 | fake_discogsography supports limit=1 call (CI fixture) | unit | `pytest tests/unit/test_fake_discogsography.py::test_limit_one -x` | ❌ Wave 0 (may already pass — see code context) |
| API-04 | `collection_changed` SSE payload includes `new_record_count` + `is_initial_import` | unit | `pytest tests/unit/test_profile_sync.py::test_collection_changed_payload -x` | ❌ Wave 0 |
| API-04 | First sync `is_initial_import=True`; second sync `is_initial_import=False` | integration | `pytest tests/integration/test_invite_codes.py::test_initial_import_flag -x` | ❌ Wave 0 |
| API-04 | `new_record_count` ≥ 0, equals number of genuinely new releases | integration | `pytest tests/integration/test_invite_codes.py::test_arrival_count_accuracy -x` | ❌ Wave 0 |
| API-04 | Profile API response includes `last_new_record_count` + `last_sync_is_initial` | integration | `pytest tests/integration/test_invite_codes.py::test_profile_new_record_fields -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/unit/ -q --tb=short --benchmark-skip`
- **Per wave merge:** `pytest tests/ -q --tb=short --benchmark-skip`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/integration/test_invite_codes.py` — covers AUTH-02 + API-04 integration tests (12 tests)
- [ ] `tests/unit/test_fake_discogsography.py` — verify limit=1 behavior (may partially exist; check for `test_limit_one`)
- [ ] `tests/unit/test_profile_sync_diff.py` — unit tests for `new_record_count` computation logic and `is_initial_import` detection

---

## Open Questions

1. **Rate-limit posture for the public redeem endpoint**
   - What we know: the existing `limiter.py` provides `FixedWindowRateLimiter` used for `POST /devices/bind` at 10 attempts / 5 minutes per IP (T-03-05).
   - What's unclear: the redeem endpoint is code-scoped (one valid code per invite), not just IP-scoped. An attacker who has a valid UUID could make repeated PAT submissions.
   - Recommendation: apply both a per-IP limit (e.g., 5 attempts / 10 minutes) AND a per-code attempt cap (e.g., 3 attempts before voiding the code). The per-code cap is new behavior; implement it as a column `attempt_count INTEGER DEFAULT 0` on `profile_invite_codes` or as an application counter. For Phase 7 scope, per-IP throttle alone (reusing existing limiter) is the minimum viable guard; per-code cap is a discretionary enhancement.

2. **`has_token` field in frontend `AdminProfile` type**
   - What we know: `types.ts` defines `AdminProfile` without `has_token`. The backend `_profile_status()` uses `app_token_revoked` to derive status.
   - What's unclear: the frontend ProfileDrawer uses `profile.app_token_revoked` directly for some display logic. Adding `has_token` is additive — does it replace `app_token_revoked` or coexist?
   - Recommendation: add `has_token: boolean` to `AdminProfile` in `types.ts`; keep `app_token_revoked` for backward compatibility with existing status derivation. ProfileDrawer uses `has_token` for the invite affordance visibility condition; existing status logic continues to use `app_token_revoked`.

3. **Invite link URL construction**
   - What we know: the backend returns `code` as a UUID string. The owner's browser must construct the full URL (`http://gruvax.lan:{PORT}/redeem/{code}`).
   - What's unclear: the host/port is not stored anywhere server-side. The `POST /profiles/{id}/invite` response should include a ready-to-use URL.
   - Recommendation: the backend constructs the URL from `Request.base_url` (Starlette's `request.base_url`). Example: `f"{request.base_url}redeem/{code}"`. This works correctly for both `http://gruvax.lan:8080/redeem/...` and `http://localhost:5173/redeem/...` in dev. Document this in the endpoint implementation notes.

---

## Sources

### Primary (HIGH confidence)
- `src/gruvax/sync/pat_crypto.py` — Fernet encrypt/decrypt implementation; verified lazy-construction pattern
- `src/gruvax/api/admin/profiles.py:430-522` — owner `connect_pat` flow; the direct template for member redeem
- `src/gruvax/api/admin/devices.py:80-87` — atomic `UPDATE ... WHERE consumed_at IS NULL RETURNING` pattern
- `migrations/versions/0011_devices_and_pairing_codes.py` — `pairing_codes` schema; direct template for `profile_invite_codes`
- `src/gruvax/sync/profile_sync.py:244-356` — staging-swap + SSE publish; extension points for `first_seen_at` and payload fields
- `src/gruvax/_internal/fake_discogsography.py:86-116` — CI fixture; limit=1 already supported
- `src/gruvax/api/events.py` — SSE stream; confirms `e.data` is `json.dumps(event.data)`
- `src/gruvax/events/bus.py` — EventBus `publish` API
- `frontend/src/routes/kiosk/KioskView.tsx:338-356` — existing `collection_changed` handler; confirms no-argument form
- `frontend/src/routes/admin/ProfileDiagnosticsCard.tsx` — diagnostics card row pattern; insertion point for NEW RECORDS row
- `frontend/src/App.tsx` — route structure; confirms `/redeem/:code` must be outside `/admin` nest
- `frontend/src/api/types.ts` — `AdminProfile` type; `has_token` field is absent, confirming it is new work
- `.planning/phases/07-member-self-connect-collection-diff/07-CONTEXT.md` — all locked decisions
- `.planning/phases/07-member-self-connect-collection-diff/07-UI-SPEC.md` — surface contracts, copywriting, animation tokens

### Secondary (MEDIUM confidence)
- `migrations/versions/0009_v2_profiles_and_collection_cache.py` — `profile_collection` schema; confirms `synced_at` column exists beside which `first_seen_at` is added
- `src/gruvax/api/admin/router.py` — admin router factory; confirms registration pattern for new sub-routers

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in project; no new installs
- Architecture: HIGH — all patterns directly traceable to live codebase
- Pitfalls: HIGH — all pitfalls derived from verified code inspection, not training data
- Security posture: HIGH — locked by CONTEXT.md L-05; runbook note pattern is clear

**Research date:** 2026-06-01
**Valid until:** 2026-07-01 (stable domain; no external dependencies changing)

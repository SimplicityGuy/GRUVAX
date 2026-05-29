# Phase 3: Devices + pairing - Context

**Gathered:** 2026-05-28
**Status:** Ready for planning

<domain>
## Phase Boundary

A headless RPi kiosk pairs to a profile in **<30 seconds** end-to-end via a 4-digit code shown on its own screen; the binding **survives reboot**; and the owner can rename / change-profile / unbind / revoke devices from the mobile PIN-gated admin UI. Device binding is a **new, independent binding model** stored in the `devices` table and keyed by an **HttpOnly fingerprint cookie** — distinct from P2's non-HttpOnly browser-session `gruvax_browse_binding` cookie. The two models coexist; for a paired device, device binding is authoritative.

**In scope (P3):**
- `devices` + `pairing_codes` schemas (new Alembic migration) with the partial-unique active-row indexes and `consumed_at` one-shot guard from the refined spec §Data Model.
- Fingerprint cookie middleware: server-issued opaque value, **HttpOnly + SameSite=Strict**, long max-age (persists across reboot), `Secure` when TLS lands.
- Pairing endpoints: kiosk `POST /api/devices/pairing-codes` (generate 4-digit code, 5-min TTL), kiosk `GET /api/devices/me` (state poll), admin `POST /api/admin/devices/bind` (PIN-gated, code→device row + mark consumed).
- Kiosk **`/pair` route** (Nordic Grid, large DM Mono digits, 5-min countdown, auto-reroll on expiry, polls `/api/devices/me`).
- Devices admin UI: PENDING / PAIRED / REVOKED groupings + per-device bottom-sheet drawer (rename / change-profile / unbind / revoke), reusing v1's `NumericKeypad` for the "Enter code" entry.
- Per-profile **resolution-from-device-binding** path: search / locate / illuminate / SSE-subscribe derive `profile_id` from the device when a paired fingerprint is present.
- Real-time device lifecycle delivery over the existing per-profile SSE channel + a per-request revoke guard.
- Committed Pi provisioning artifact: `start-kiosk.sh` + `systemd --user` unit + `deploy/kiosk` README; reboot-persistence test coverage.

**Out of scope (other phases / milestones):**
- Nightly background sync scheduler + cadence config, 401 reauth UI, per-profile `/admin/diagnostics` cards, soft-delete cache-purge **background task**, "Sync now" completion-toast polish — all **P4**.
- QR-code pairing (DEV-04 → v2.1), OAuth2 device-authorization grant (AUTH-01 → v2.2), per-profile self-connect PAT (v2.1).
- Real LED/WS2812B hardware — independent hardware milestone.

</domain>

<decisions>
## Implementation Decisions

### Pairing entry & kiosk routing
- **D3-01: Kiosk enters pairing via a dedicated `/pair` route.** The Pi provisioning launches Chromium pointed at `http://gruvax.lan/pair`. Casual LAN browsers/phones hit `/` and get P2's browser picker exactly as before — they never accidentally land on a pairing screen. Chosen over auto-pairing any unpaired screen (would surprise phones) and admin-only pairing (diverges from the spec's kiosk-shows-code flow + the <30s UX).
- **D3-02: `/pair` is also reachable from the browser UI.** Add a "Pair this screen as a device" affordance on the `/select` picker **and** the 0-profile onboarding screen that routes to `/pair`. Lets the owner convert any screen into a permanent device without re-provisioning and keeps the feature discoverable. Kiosk provisioning still defaults its URL to `/pair`.
- **D3-03 (routing precedence):** An already-paired device that loads `/` or `/pair` goes straight to the bound-profile search UI (no picker, no code). Exact redirect/short-circuit shape is planner discretion, but the rule is: paired-with-profile → search; unpaired/unknown device → `/pair`; orphaned device (see D3-05) → picker.

### Device vs browse-binding precedence
- **D3-04: Device binding wins, resolved server-side.** Extend `GET /api/session`: when the request's fingerprint maps to a **paired** device, the server returns that device's `profile_id` as `bound_profile_id` plus a `device_id` and a "paired device" flag, overriding/ignoring `gruvax_browse_binding`. The SPA hides the picker **and** the "Switch profile" corner button for paired devices (spec: "Devices ignore this"). Honors "derive binding server-side, never trust client" (P2 D2-04/D2-10). `GET /api/devices/me` **coexists** as the kiosk's pairing-state poll endpoint (`{state, profile_id}`); `GET /api/session` is the authoritative SPA bootstrap.
- **D3-05: Resolution precedence rule = `devices.profile_id` if non-NULL, else browse-binding/picker.** A paired device with a live profile is locked to it. A device whose bound profile was **soft-deleted** (profile_id detached to NULL per `ON DELETE SET NULL` semantics, applied at soft-delete time) is **orphaned** — it falls back to behaving like a browser (shows the `/select` picker) until an admin **reassigns** it, which rewrites `devices.profile_id`. This satisfies criterion #3's "kiosks revert to the profile-picker" without creating an override loop, and avoids letting any PIN-free LAN user reassign a wall-mounted device via the picker.
- **`device_id` is non-secret** and may be returned by `GET /api/session`; the **fingerprint stays HttpOnly** (never readable by JS). The SPA filters its own lifecycle events by `device_id`.

### Real-time revoke / reassign delivery
- **D3-06: Device lifecycle events ride the device's current profile SSE channel.** Publish `device_reassigned` / `device_revoked` on `/api/events/{profile_id}` for the channel the device is subscribed to **right now** (its current/old profile). The kiosk filters "is this my `device_id`?" — on `device_reassigned`→self it re-bootstraps `GET /api/session` and reconnects to the new profile's channel (auto-reload, criterion #3); on `device_revoked`→self it routes to `/pair`. Reuses P2's per-profile `EventBus` registry (D2-05); **no new SSE infra**. Chosen over a dedicated per-device channel (doubles connections + a parallel device-keyed bus) and poll-only (doesn't satisfy "via SSE").
- **D3-07: Authoritative revoke guard = per-request device check + SSE push (belt-and-suspenders).** The profile-resolution dependency re-checks the device on **every** per-profile request (search / locate / illuminate / SSE-subscribe): a fingerprint mapping to a **revoked or unknown** device → **401/403** → SPA routes to `/pair`. This backstops idle wall-mounted kiosks and stale tabs whose SSE dropped, alongside the D3-06 push. Directly serves security touchpoint #5 (per-profile data isolation; derive from binding, never trust client).

### Pi provisioning artifact scope
- **D3-08: Ship committed provisioning artifacts.** A real `start-kiosk.sh` (Chromium `--kiosk --noerrdialogs --disable-infobars --no-first-run --password-store=basic --ozone-platform=wayland --user-data-dir=<persistent path> --app=http://gruvax.lan/pair`), a `systemd --user` unit (`Restart=always`, small `RestartSec`), and a `deploy/kiosk` README. Matches the CLAUDE.md "Recommended Stack — Raspberry Pi Kiosk" spec. Chosen over document-only (relies on owner transcription) and a full idempotent provisioner (overkill for one home Pi, untestable in CI).
- **D3-09: Reboot-persistence verified by an automated persistent-profile browser test + a cookie-attribute unit test.** A Playwright test (webapp-testing toolkit is available) launches Chromium with a persistent `user-data-dir`, pairs, closes the context, **relaunches with the same dir**, and asserts the fingerprint cookie + bound profile survive — simulating a reboot. A backend unit test asserts cookie attributes: **HttpOnly + SameSite=Strict + long max-age** (and `Secure` flag toggling on TLS). Real reboot on hardware is a **documented manual smoke step** in the deploy README.

### Locked by the refined spec (flow into planning as-is — not re-decided here)
- `devices` / `pairing_codes` table shapes + `idx_devices_fingerprint_active`, `idx_devices_profile_active`, `idx_pairing_codes_expires` (spec §Data Model).
- 4-digit `CHAR(4)` code, 5-min TTL (`expires_at = created_at + 5min`), `consumed_at` one-shot guard, auto-reroll on expiry (spec §RPi Pairing Flow A).
- Brute-force resistance recipe: 5-min TTL × 10k keyspace × `consumed_at` one-shot × admin PIN-gating on `/api/admin/devices/bind` × rate-limit on bind (security touchpoint #4); concurrent bind on same code → first wins, second sees "Code not found".
- Admin UI groupings PENDING / PAIRED / REVOKED + drawer; reuse v1 `NumericKeypad` for "Enter code" (spec §Profile Manager Admin UI → Devices section; DEV-03).

### Claude's / planner's discretion
- Auto-reroll mechanics (client-driven re-request on countdown-zero vs server-side) and cleanup of expired `pairing_codes` rows.
- Code-collision handling on generation (regenerate on PK clash with an un-consumed code) — trivial at household scale.
- `devices.last_seen_at` touch frequency (every request vs throttled).
- Rate-limit cadence/threshold on `/api/admin/devices/bind` (reuse v1's login rate-limiter pattern).
- Exact `/pair` redirect/short-circuit shape for an already-paired device (D3-03).
- Drawer copy, countdown styling specifics, "Pair this screen" button placement — Nordic Grid / UI-spec discretion (a `/gsd-ui-phase 3` pass is available; ROADMAP UI hint = yes).
- Fingerprint cookie name, opaque-value generation (e.g., `secrets.token_urlsafe`), and persistent `user-data-dir` path on the Pi.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### v2.0 design specs (authoritative)
- `docs/superpowers/specs/2026-05-26-v2-multi-user-collections-refined.md` — **Refined design spec.** Load-bearing for P3: §Data Model → `devices` + `pairing_codes` (exact DDL + indexes); §RPi Pairing Flow A (the 4-digit-code sequence diagram + failure modes); §Profile Manager Admin UI → Devices section (PENDING/PAIRED/REVOKED + drawer); §Browser Session Profile Picker (devices ignore the Switch-profile button); §Phase Decomposition → **P3** (exit criteria + "Pi setup script — persist Chromium `--user-data-dir`"); §Constraints → New in v2.0; §Security review touchpoints (#3 fingerprint cookie hardening, #4 pairing-code brute-force, #5 per-profile isolation); §Risks #2 (cookie persistence across reboot).
- `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` — Original SPEC; superseded by the refined version on any contradiction.

### Phase carry-forward (load first — P3 builds directly on P2)
- `.planning/phases/02-multi-profile-migration-profile-manager/02-CONTEXT.md` — All P2 decisions cascade. Especially **D2-04** (`/api/events/{profile_id}` + session validation; never trust client `profile_id`), **D2-05** (per-profile `EventBus` registry — P3 publishes device events here), **D2-07/D2-08** (`/select` picker + `GET /api/session` bootstrap — P3 extends this for device binding), **D2-09** (Switch-profile corner button — hidden for paired devices), **D2-10** (independent non-HttpOnly `gruvax_browse_binding` cookie — the model the HttpOnly fingerprint cookie coexists with), **D2-11** (bottom-sheet drawer admin pattern), **D2-13** (202+poll convention reused by device bind/poll).
- `.planning/phases/01-walking-skeleton-api-client-single-profile-sync/01-CONTEXT.md` — P1 foundations (profiles schema, default-profile seed, sync state machine).

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — P3 owns **DEV-01** (devices + pairing_codes + fingerprint cookie), **DEV-02** (device-to-profile binding + admin UI), **DEV-03** (4-digit code pairing flow A).
- `.planning/ROADMAP.md` §"Phase 3: Devices + pairing" — the 5 success criteria the verifier scores against.
- `.planning/PROJECT.md` — Current State + v2.0 milestone framing + Key Decisions table.
- `.planning/STATE.md` — current position (Phase 2 complete, ready to plan Phase 3).

### Intel (ingested, pre-synthesized)
- `.planning/intel/SYNTHESIS.md` — entry point for the ingested intel.
- `.planning/intel/constraints.md` / `decisions.md` / `requirements.md` / `context.md` — design-time constraints (cross-profile leakage impossible by construction; per-profile staleness) + risks (risk #2 = cookie persistence across reboot, risk #6 = iOS Safari cookies).

### Existing code P3 modifies or extends
- `src/gruvax/api/session.py` — `GET /api/session` bootstrap; **P3 extends it** to fold in device binding (D3-04) and return `device_id`.
- `src/gruvax/auth/sessions.py` — cookie helpers; `BROWSE_BINDING_COOKIE` (non-HttpOnly) lives here. P3 adds the **HttpOnly** fingerprint cookie helper + middleware alongside (do NOT couple to the browse-binding cookie — D3-04).
- `src/gruvax/api/deps.py` — `get_pool`, `require_admin`, per-profile resolution deps; P3 adds device-aware profile resolution + the per-request revoke guard (D3-07).
- `src/gruvax/events/bus.py` + `src/gruvax/api/events.py` — per-profile `EventBus` + `/api/events/{profile_id}` SSE; P3 publishes `device_reassigned`/`device_revoked` here (D3-06); preserve Pitfall 10 (SSE depends only on the bus, never `get_pool`).
- `frontend/src/routes/admin/NumericKeypad.tsx`, `PinOverlay.tsx`, `AdminShell` — reused for the devices admin "Enter code" + PIN gate + nav.
- `frontend/src/routes/kiosk/KioskView.tsx` + `frontend/src/App.tsx` — new `/pair` route; KioskView gains paired-device awareness (hide Switch button; re-bootstrap on `device_reassigned`).
- `migrations/versions/` — new migration (0011) adding `devices` + `pairing_codes`; Alembic upgrade↔downgrade round-trip CI invariant must hold (current head = 0010 per memory note).
- `scripts/` — sibling location for any new CLI helpers; new `deploy/kiosk/` directory for `start-kiosk.sh` + systemd unit + README (D3-08).

### UI direction
- `.claude/skills/sketch-findings-gruvax/SKILL.md` — validated Nordic Grid CSS patterns + mobile-first sheet/drawer direction; drives the devices admin drawer + the `/pair` countdown screen styling.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`GET /api/session` bootstrap** (`src/gruvax/api/session.py`) — already the SPA's routing source of truth; P3 extends rather than replaces it (D3-04).
- **Per-profile `EventBus` registry** (P2 D2-05, `src/gruvax/events/bus.py`) — device lifecycle events publish onto the existing profile channels; no new bus type (D3-06).
- **`NumericKeypad` / `PinOverlay` / `AdminShell` + bottom-sheet drawer** (`frontend/src/routes/admin/`) — the devices admin "Enter code" + PIN gate + per-device drawer reuse v1 patterns (D2-11).
- **`require_admin`** (`src/gruvax/api/deps.py`) — gates `POST /api/admin/devices/bind` and every `/api/admin/devices/*` mutation (security touchpoint #8).
- **Cookie helper pattern** (`set_browse_binding_cookie` in `auth/sessions.py`) — template for the new HttpOnly fingerprint cookie setter (different attributes: HttpOnly=True, longer max-age).
- **v1 login rate-limiter** — pattern to reuse for `/api/admin/devices/bind` brute-force throttling (security touchpoint #4).

### Established Patterns
- **No live probes on `/api/health`; binding derived server-side, never trusted from the client** — D3-04/D3-07 follow this.
- **Per-profile SSE depends ONLY on the bus, never `get_pool`** (Pitfall 10) — preserved when adding device events.
- **Parameterized `%s` SQL, no f-string interpolation** (bandit B608) — all device/pairing queries follow it.
- **Alembic upgrade↔downgrade round-trip enforced in CI** — the `devices`/`pairing_codes` migration must honor it.
- **PAT/secret redaction in structured logs** — the fingerprint value is a credential-equivalent; do not log it plaintext.

### Integration Points
- **`GET /api/session` extension** — device-binding resolution + `device_id` exposure (D3-04).
- **New fingerprint cookie middleware** — issues the HttpOnly cookie; independent of the admin + browse-binding cookies (D3-04).
- **Device-aware profile-resolution dependency** — per-request device validity check feeding search/locate/illuminate/SSE-subscribe (D3-07).
- **`device_reassigned`/`device_revoked` events** on the per-profile bus (D3-06).
- **`/pair` SPA route** + "Pair this screen" affordances on `/select` + onboarding (D3-01/D3-02).
- **`/admin/devices`** screen + endpoints under `/api/admin/devices/*`; kiosk endpoints under `/api/devices/*`.
- **`deploy/kiosk/`** new directory: `start-kiosk.sh` + `gruvax-kiosk.service` (`systemd --user`) + README (D3-08).

</code_context>

<specifics>
## Specific Ideas

- **Two binding models, deliberately different cookies:** P2's `gruvax_browse_binding` is **non-HttpOnly** (SPA reads it for the SSE URL); P3's fingerprint cookie is **HttpOnly + SameSite=Strict**. They are never coupled — device binding is resolved entirely server-side (D3-04), and the precedence rule (D3-05) makes "device profile if set, else browse cookie" the single source of routing truth.
- **The asymmetry in criterion #3 is intentional and honored:** *revoke* may take effect "on its next request" (covered by the per-request guard D3-07), while *reassign* "auto-reloads via SSE" (covered by the push D3-06). Plan both paths; don't collapse them into one mechanism.
- **`/pair` is the kiosk's provisioned home** (D3-01/D3-08): the Chromium `--app=` URL is `http://gruvax.lan/pair`, which ties the routing decision (Area 1) to the provisioning artifact (Area 4) — they should be planned together.
- **Reboot-persistence is the one criterion CI can't reach with real hardware** — the Playwright persistent-`user-data-dir` round-trip (D3-09) is the closest faithful simulation; treat the cookie-attribute unit test as the contract and the browser test as the integration proof.

</specifics>

<deferred>
## Deferred Ideas

### Surfaced during discussion / spec but belong in other phases or milestones
- **QR-code RPi pairing** (kiosk shows QR → admin scans) — **DEV-04 → v2.1**. P3 ships the 4-digit-code flow A only.
- **OAuth2 device-authorization grant** (no PAT crosses the household) — **AUTH-01 → v2.2**.
- **Soft-delete cache-purge background task** (async purge of `profile_collection` rows) — **P4**. P3's profile-soft-delete path only **detaches** bound devices (sets `devices.profile_id` NULL) so kiosks revert to the picker.
- **401 reauth UI, per-profile `/admin/diagnostics` cards, nightly sync scheduler, "Sync now" toast polish** — all **P4**.
- **Full idempotent Pi provisioner** (apt install, labwc autostart, cursor-hide, screen-blank config) — considered, deferred; P3 ships the kiosk-launch script + unit + doc only (D3-08).

### Reconciled risks (from refined spec)
- **Fingerprint cookie persistence across RPi reboot (risk #2)** — mitigated by D3-08 (persistent `--user-data-dir`) + D3-09 (automated round-trip test); fallback if cookies don't persist = re-pair on each reboot (acceptable but worse UX).
- **iOS Safari same-site cookies (risk #6)** — N/A for the HttpOnly device cookie path (kiosk is Chromium); all traffic is same-site to `gruvax.lan`.

### None additionally
Discussion stayed within phase scope; no scope-creep ideas to capture.

</deferred>

---

*Phase: 3-devices-pairing*
*Context gathered: 2026-05-28*

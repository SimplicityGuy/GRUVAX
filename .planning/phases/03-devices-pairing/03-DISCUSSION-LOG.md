# Phase 3: Devices + pairing - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-28
**Phase:** 3-devices-pairing
**Areas discussed:** Pairing entry & kiosk routing, Device vs browse-binding precedence, Real-time revoke/reassign delivery, Pi provisioning artifact scope

---

## Pairing entry & kiosk routing

### Q1 — What initiates the pairing flow on a fresh screen?

| Option | Description | Selected |
|--------|-------------|----------|
| Kiosk opens a /pair route | Pi provisioning points Chromium at gruvax.lan/pair; casual browsers hit / and get the P2 picker. Ties to provisioning (Area 4). | ✓ |
| Auto-pair any unpaired screen | Any fingerprinted screen with no paired device row auto-renders pairing — but a phone would also see it; conflicts with P2 picker. | |
| Pair from admin only | No kiosk-initiated code; diverges from the spec flow + <30s UX. | |

**User's choice:** Kiosk opens a /pair route
**Notes:** —

### Q2 — Should /pair also be reachable from the browser picker?

| Option | Description | Selected |
|--------|-------------|----------|
| Button on /select too | "Pair this screen as a device" affordance on /select + onboarding routes to /pair; kiosk URL still defaults to /pair. Discoverable. | ✓ |
| Kiosk URL only | /pair entered only by URL/provisioning; picker visually identical to P2. | |

**User's choice:** Button on /select too
**Notes:** —

---

## Device vs browse-binding precedence

### Q1 — How should device binding relate to gruvax_browse_binding?

| Option | Description | Selected |
|--------|-------------|----------|
| Device binding wins, server-side | GET /api/session extended to return device's profile_id (+ device_id, paired flag), overriding browse cookie; SPA hides picker + Switch button. /api/devices/me coexists as pairing poll. | ✓ |
| Separate device endpoint | Keep /api/session browser-only; kiosk calls GET /api/devices/me first and decides precedence client-side. | |
| Device writes browse cookie | Pairing sets gruvax_browse_binding to the device's profile; reuses P2 path but couples the two cookies. | |

**User's choice:** Device binding wins, server-side
**Notes:** —

### Q2 — Precedence rule given orphaned devices (criterion #3)?

| Option | Description | Selected |
|--------|-------------|----------|
| Device profile if set, else browse cookie | Use devices.profile_id when non-NULL; orphaned device (profile soft-deleted → NULL) falls back to picker until admin reassigns. No override loop. | ✓ |
| Orphaned device returns to /pair | Detached device drops to pairing screen; contradicts "revert to the profile-picker" wording + adds friction. | |
| Picker re-binds the device itself | Orphaned device's picker tap rewrites devices.profile_id PIN-free; weakens admin-gated binding. | |

**User's choice:** Device profile if set, else browse cookie
**Notes:** —

---

## Real-time revoke/reassign delivery

### Q1 — How to push device lifecycle events to the kiosk over SSE?

| Option | Description | Selected |
|--------|-------------|----------|
| Device events on current profile channel + client filter | Publish device_reassigned/device_revoked on the device's current /api/events/{profile_id}; kiosk filters by its own device_id. Reuses P2 EventBus; no new infra. | ✓ |
| Dedicated per-device SSE channel | New /api/events/device/{device_id} bus; kiosk holds two SSE connections. Cleaner but heavier. | |
| Poll-only for lifecycle | Existing /api/devices/me poll + next-request guard; doesn't satisfy "via SSE". | |

**User's choice:** Device events on current profile channel + client filter
**Notes:** —

### Q2 — Authoritative guard so a revoked device can't keep using its old profile?

| Option | Description | Selected |
|--------|-------------|----------|
| Per-request device check + SSE push | Profile-resolution dep re-checks device each request (revoked/unknown → 401/403 → /pair) PLUS device_revoked SSE push for idle kiosks. Belt-and-suspenders; security touchpoint #5. | ✓ |
| SSE push only | Rely solely on the SSE event; a stale tab whose SSE dropped could keep querying. | |

**User's choice:** Per-request device check + SSE push
**Notes:** —

---

## Pi provisioning artifact scope

### Q1 — What should P3 deliver on the Pi/kiosk side?

| Option | Description | Selected |
|--------|-------------|----------|
| Committed script + unit + deploy doc | Real start-kiosk.sh (Chromium kiosk flags + persistent --user-data-dir + --app=http://gruvax.lan/pair) + systemd --user unit + deploy/kiosk README. | ✓ |
| Document-only | Provisioning steps in a doc; no runnable script. | |
| Full idempotent provisioner | End-to-end Pi install script; heavy + untestable in CI. | |

**User's choice:** Committed script + unit + deploy doc
**Notes:** —

### Q2 — How to verify reboot-persistence without a Pi in CI?

| Option | Description | Selected |
|--------|-------------|----------|
| Automated persistent-profile browser test + cookie-attr unit test | Playwright: pair → close → relaunch same user-data-dir → assert cookie+binding survive. Plus backend cookie-attribute test (HttpOnly+SameSite=Strict+max-age). Manual reboot = doc smoke step. | ✓ |
| Cookie-attribute unit test only | Backend attribute assertions; persistence left to manual hardware smoke test. | |
| Manual smoke test on hardware only | Documented Pi smoke test; no automated coverage. | |

**User's choice:** Automated persistent-profile browser test + cookie-attr unit test
**Notes:** —

---

## Claude's Discretion

- Auto-reroll mechanics + expired `pairing_codes` cleanup.
- Code-collision handling on generation.
- `devices.last_seen_at` touch frequency.
- Rate-limit cadence/threshold on `/api/admin/devices/bind` (reuse v1 login limiter).
- Exact `/pair` redirect for an already-paired device.
- Drawer copy, countdown styling, "Pair this screen" placement (deferrable to `/gsd-ui-phase 3`).
- Fingerprint cookie name + opaque-value generation + persistent `user-data-dir` path.

## Deferred Ideas

- QR-code pairing (DEV-04 → v2.1); OAuth2 device-grant (AUTH-01 → v2.2).
- Soft-delete cache-purge background task → P4 (P3 only detaches devices).
- 401 reauth UI, per-profile diagnostics cards, nightly sync, "Sync now" toast → P4.
- Full idempotent Pi provisioner → deferred (P3 ships launch script + unit + doc only).

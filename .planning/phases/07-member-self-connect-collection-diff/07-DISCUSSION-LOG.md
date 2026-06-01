# Phase 7: Member Self-Connect + Collection Diff - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-31
**Phase:** 7-member-self-connect-collection-diff
**Areas discussed:** Invite link delivery + TTL, Redeem page UX, "N new records" semantics + placement, Invite lifecycle + edge cases

---

## Invite link delivery + TTL

| Option | Description | Selected |
|--------|-------------|----------|
| 1 hour | Async-share friendly, limited exposure window | ✓ |
| 15 minutes | "Do it now while I'm with you"; risk of lapse | |
| 24 hours | Most forgiving; larger exposure window | |

**User's choice:** 1 hour TTL.

| Option | Description | Selected |
|--------|-------------|----------|
| Copy-to-clipboard | "Copy link" button; owner pastes into any app | ✓ |
| Native share sheet (Web Share API) | OS share sheet; flaky in kiosk Chromium | |
| Copy link + QR | Adds in-person QR (QR lib is Phase 8) | |

**User's choice:** Copy-to-clipboard.
**Notes:** Link is `/redeem/:opaque-uuid`, outside the admin PIN gate.

---

## Redeem page UX (member-facing)

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-start initial sync | Mirrors owner connect flow; member's job done | ✓ |
| Connect only, owner syncs later | Simpler redeem; collection appears after owner acts | |

**User's choice:** Auto-start initial sync on successful redeem.

---

## "N new records" semantics + placement

| Option | Description | Selected |
|--------|-------------|----------|
| Arrivals via first_seen_at | Newly-arrived rows; removals don't subtract; ≥ 0 | ✓ |
| Net delta (new_count − old_count) | Simple two COUNT(*)s; can go negative; misleading | |

**User's choice:** Arrivals via `first_seen_at`.

| Option | Description | Selected |
|--------|-------------|----------|
| Show as initial import | First sync reads "Imported N records", not "N new" | ✓ |
| Treat identically | First sync shows full collection size as "new" | |

**User's choice:** First sync = initial import (special-cased).

| Option | Description | Selected |
|--------|-------------|----------|
| Until the next sync | Persistent, stateless render from last sync's count | ✓ |
| Transient — fades after viewing | Timely toast/badge; missable | |

**User's choice:** Persist until the next sync.

---

## Invite lifecycle + edge cases

| Option | Description | Selected |
|--------|-------------|----------|
| New voids old — one active invite | New link invalidates prior unredeemed code | ✓ |
| Allow multiple concurrent invites | Each link valid until own TTL/redeem | |

**User's choice:** One active invite per profile (new voids old).

| Option | Description | Selected |
|--------|-------------|----------|
| Replace/rotate the token | Redeem overwrites stored PAT; supports re-connect | ✓ |
| Refuse if token already present | Rotation stays owner-driven | |

**User's choice:** Redeem replaces/rotates the token.

---

## Claude's Discretion
- Abuse posture on the public redeem endpoint (per-code attempt cap / per-IP throttle) — flagged for the researcher/security pass.
- `has_token` derivation from `app_token_encrypted IS NOT NULL AND NOT app_token_revoked` (no redundant column).
- Redeem error copy (Nordic Grid voice) and outstanding-invite cleanup on profile delete.
- Exact admin-UI placement of the "Copy invite link" affordance.

## Deferred Ideas
- QR for invite/redeem — revisit with DEV-04 (Phase 8).
- Native Web Share API for the invite link.
- Set-level "which records changed" diff — out of scope per API-04 (count only).

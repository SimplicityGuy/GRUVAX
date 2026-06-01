# Phase 8: QR Pairing + Privacy + Recently-Pulled - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-01
**Phase:** 8-qr-pairing-privacy-recently-pulled
**Areas discussed:** QR encode & landing, Recently-pulled UX, Reset-kiosk scope, History clear triggers

---

## QR encode & landing

| Question | Option | Selected |
|----------|--------|----------|
| What does the QR encode? | **Same 4-digit code in URL** | ✓ |
| | Separate opaque nonce | |
| Where does scanning land? | **PIN-gated admin bind page** | ✓ |
| | Public prefilled bind page | |
| QR re-render cadence | **Tied to the 5-min reroll** | ✓ |
| | Faster independent rotation | |
| How does pairing complete? | **Explicit one-tap confirm** | ✓ |
| | Auto-submit on load | |

**Notes:** All four recommendations taken. The 4-digit code already satisfies REQUIREMENTS'
"opaque short-TTL code, never a credential," so a separate nonce path was rejected as
unjustified ceremony — this also makes "both paths → same `complete_pairing` / identical
audit" automatic. Landing on the PIN-gated admin bind page preserves today's bind security
model (a public-kiosk QR scan still can't bind without the PIN).

---

## Recently-pulled UX

| Question | Option | Selected |
|----------|--------|----------|
| What enters the list? | **Only a successful locate** | ✓ |
| | Every committed search | |
| Tapping a chip | **Re-locate that record** | ✓ |
| | Non-interactive display | |
| Max chips | **~8, most-recent-first, deduped** | ✓ |
| | ~5 | |
| | ~15 | |
| Placement | **Persistent strip below result** | ✓ |
| | Only on idle / empty state | |
| | You decide | |

**Notes:** "Recently-pulled" reads as actually-located records (not typo searches). The
list is a tappable jump-back shortcut, capped at ~8 deduped chips, in a persistent strip
below the result (exact visual deferred to UI phase).

---

## Reset-kiosk scope

| Question | Option | Selected |
|----------|--------|----------|
| What does Reset clear? | **History + search only** | ✓ |
| | Also drop profile selection | |
| Admin-session detection | **Client-side adminStore flag** | ✓ |
| | Server admin_active flag | |
| Accidental-tap guard | **Lightweight confirm** | ✓ |
| | Instant, no confirm | |
| Prominence | **Subtle / low-emphasis** | ✓ |
| | Clear labeled button | |
| | You decide | |

**Notes:** Reset is client-side only (PRIV-04) — clears the local UI session, keeps the
device paired and profile bound. Hidden via the same SPA's `adminStore.isLoggedIn`
(per-browser, correct semantics — a server-wide flag would wrongly hide it when the owner
is in admin on their phone). Lightweight confirm prevents accidental wipes.

---

## History clear triggers

| Question | Option | Selected |
|----------|--------|----------|
| Storage | **sessionStorage-backed** | ✓ |
| | Pure in-memory | |
| Idle timeout duration | ~10 minutes | |
| | ~5 minutes | |
| | **~15 minutes** | ✓ |
| On idle / session end | **Return to resting screen** | ✓ |
| | Clear list, keep last result | |

**Notes:** `sessionStorage` matches success criterion 2 exactly (survives reload, dies on
hard Chromium restart) and stays excluded from the localStorage `persist` slice (PRIV-01).
A ~15-min idle timeout (none exists today) satisfies SRCH-09's idle-clear trigger and is
forgiving of a user who pauses to walk to the shelf; idle/session-end returns to the
resting screen so no prior lookup is left on display.

---

## Claude's Discretion

- QR library choice (frontend `react-qr-code` vs backend `qrcode` endpoint) — lean
  frontend-only; flagged for researcher.
- PRIV-02 CI log-assertion test shape (capture stream, assert query term absent; reuse the
  `redact_dscg_tokens` processor pattern for any new `q`-adjacent logging).
- Identical-audit-entry plumbing between the scan and typed bind paths.
- Recently-pulled chip content (artist/title/catalog, DM Mono catalog numbers) +
  truncation on the 7" display — UI phase.
- Which interactions reset the idle timer — any user interaction.

## Deferred Ideas

- QR for the Phase 7 invite/redeem link — library lands here, but invite-QR remains its
  own follow-up, not Phase 8 scope.
- Separate faster-rotating opaque QR nonce — rejected for this phase (D-01); revisit only
  if the threat model changes or QR leaves the LAN.
- Server-persisted / set-level search history — explicitly out of scope (PRIV-01/03).

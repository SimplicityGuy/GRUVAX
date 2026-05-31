/**
 * DeviceLifecycle — Nordic-Grid-styled device lifecycle UI components (Phase 6, 06-02).
 *
 * Exports:
 *   RevokeNotice  — full-screen overlay shown by App.tsx when revokePending is true (D-06).
 *                   Covers any route so it works even when KioskView is not mounted.
 *   ReassignBanner — top banner shown by KioskView on device_reassigned (D-08).
 *                   Auto-dismissed after ~2.5s.
 *
 * Design contract (CLAUDE.md Nordic Grid):
 *   - ALL-CAPS Barlow Condensed for headings/labels
 *   - Sentence-case Space Grotesk for instruction body text
 *   - Tokens via CSS custom properties — no hardcoded hex values
 *   - LED-physics motion: springs on (overshoot), fades off (smooth)
 *
 * T-06-05: clearBoundProfile() + SSE cleanup (handled by App.tsx + the effect dep chain)
 * T-06-07: reassign banner name comes from authoritative GET /api/session re-fetch (D-09)
 */

import { useEffect } from 'react'
import { useSessionStore } from '../../state/sessionStore'
import './DeviceLifecycle.css'

/**
 * RevokeNotice — full-screen terminal-revoke overlay.
 *
 * Rendered by App.tsx (not KioskView) so it covers any route (D-06).
 * Heading is ALL-CAPS Barlow Condensed; body is sentence-case Space Grotesk.
 * Background: --gruvax-blue; text: --gruvax-off-white.
 * No dismiss action — auto-navigates to /pair after ~2.5s (handled by App.tsx).
 */
export function RevokeNotice() {
  return (
    <div className="device-revoke-overlay" role="alert" aria-live="assertive" aria-atomic="true">
      <div className="device-revoke-card">
        {/* Lucide-pattern warning icon — inline SVG, aria-hidden */}
        <svg
          className="device-revoke-icon"
          xmlns="http://www.w3.org/2000/svg"
          width="48"
          height="48"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
        <h1 className="device-revoke-heading">SCREEN REMOVED</h1>
        <p className="device-revoke-body">
          This screen was removed — re-pair to continue.
        </p>
      </div>
    </div>
  )
}

/**
 * ReassignBanner — "MOVED TO <Profile>" top banner on device_reassigned.
 *
 * Rendered by KioskView when reassignBanner is non-null (D-08).
 * Auto-clears via a timeout effect after ~2.5s.
 * Background: --gruvax-yellow; text: --gruvax-blue-darker.
 * Heading is ALL-CAPS Barlow Condensed.
 */
export function ReassignBanner() {
  const reassignBanner = useSessionStore((s) => s.reassignBanner)
  const setReassignBanner = useSessionStore((s) => s.setReassignBanner)

  // Auto-dismiss after ~2.5s
  useEffect(() => {
    if (!reassignBanner) return
    const timer = setTimeout(() => setReassignBanner(null), 2500)
    return () => clearTimeout(timer)
  }, [reassignBanner, setReassignBanner])

  if (!reassignBanner) return null

  return (
    <div className="device-reassign-banner" role="status" aria-live="polite">
      {/* Arrow-right icon — Lucide-pattern inline SVG, aria-hidden */}
      <svg
        className="device-reassign-icon"
        xmlns="http://www.w3.org/2000/svg"
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <polyline points="9 18 15 12 9 6" />
      </svg>
      <span className="device-reassign-text">
        MOVED TO {reassignBanner.toUpperCase()}
      </span>
    </div>
  )
}

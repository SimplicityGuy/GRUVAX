/**
 * ReauthBanner — kiosk re-auth inline banner (Phase 4 / D4-08, D4-10).
 *
 * Renders a non-blocking, persistent inline banner below StalenessBar when
 * GET /api/session returns needs_reauth: true for the bound profile.
 *
 * CRITICAL (D4-10): This banner is NON-BLOCKING — it does NOT gate the search
 * input, cube grid, or any kiosk interactivity. It is purely informational.
 *
 * Design spec (04-UI-SPEC.md Surface 5):
 * - Background: --gruvax-yellow (reauth-banner class)
 * - Text: --gruvax-blue-darker
 * - Font: Space Grotesk 18px (accessibility floor for yellow-on-darker at WCAG large-text)
 * - role="alert" + aria-live="polite"
 * - NOT dismissible
 * - Copy: plain language (T-04-03-01 mitigate — no technical jargon in user-facing text)
 *
 * Design vars only — no hardcoded hex (CLAUDE.md constraint).
 */

import './ReauthBanner.css'

export interface ReauthBannerProps {
  /** Accepted for future personalisation; not used in the current generic copy (T-04-03-01). */
  profileName?: string
}

// profileName accepted for future personalisation; static copy per T-04-03-01
export function ReauthBanner(_props: ReauthBannerProps) { // eslint-disable-line @typescript-eslint/no-unused-vars
  return (
    <div className="reauth-banner" role="alert" aria-live="polite">
      {/* AlertCircle icon — Lucide-pattern inline SVG, 18×18, aria-hidden */}
      <svg
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
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>
      <span>Shelf data may be outdated — ask the owner to update the connection.</span>
    </div>
  )
}

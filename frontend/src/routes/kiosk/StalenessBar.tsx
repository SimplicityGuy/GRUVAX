/**
 * StalenessBar — kiosk persistent banner when sync_age > 14d (OBS-06, D-01/D-02).
 *
 * Reads sync_age_seconds from the /api/health response (passed as prop from KioskView).
 * Hidden when offline (health endpoint unavailable → offline banner takes precedence)
 * or when the condition is false (< 14d or null).
 * Not dismissible — this is a persistent operational signal, not a notification.
 *
 * Nordic Grid design contract (08-UI-SPEC.md Surface 2):
 * - Background: --gruvax-yellow; text: --gruvax-blue-darker; 18px Space Grotesk weight 400
 * - Icon: inline SVG AlertTriangle (18×18), aria-hidden="true"
 * - role="alert" on mount + aria-live="polite" (fires once; no re-announce)
 * - D-02: this component MUST NOT add any no-results staleness hint
 * - T-08-17: copy is plain-language — no "sync_age_seconds", "collection_items", jargon
 */

import './StalenessBar.css'

const STALE_THRESHOLD_SECONDS = 14 * 24 * 60 * 60  // 1_209_600s — D-01 LOCKED threshold

interface Props {
  syncAgeSeconds: number | null
}

export function StalenessBar({ syncAgeSeconds }: Props) {
  // Hidden when age is unknown (health unavailable → offline banner leads)
  // or below threshold (not stale yet)
  if (syncAgeSeconds === null || syncAgeSeconds <= STALE_THRESHOLD_SECONDS) {
    return null
  }

  const days = Math.floor(syncAgeSeconds / 86400)

  return (
    <div
      className="staleness-bar"
      role="alert"
      aria-live="polite"
    >
      {/* AlertTriangle inline SVG — Lucide pattern from Settings.tsx; decorative, not load-bearing */}
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
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
        <line x1="12" y1="9" x2="12" y2="13" />
        <line x1="12" y1="17" x2="12.01" y2="17" />
      </svg>
      {/* UI-SPEC §Banner copy — sentence case, plain language, em dash, no jargon */}
      {`Collection data may be outdated — last synced ${days}d ago`}
    </div>
  )
}

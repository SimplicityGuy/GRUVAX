/**
 * OfflineBanner — kiosk persistent banner when SSE is offline-confirmed (OFF-01, D-01..D-04).
 *
 * SSE connection state is the authoritative offline trigger — NOT navigator.onLine
 * (PITFALLS 35). Render is gated on bannerVisible (offline-confirmed = !sseConnected AND
 * everConnected, gap-closure 09-05) so the banner only appears when a connection was
 * previously established and then lost — never during initial bootstrap or when the very
 * first SSE connection is rejected (e.g., 403 device_unknown).
 *
 * navigator.onLine is used only as cosmetic secondary hint for copy (D-01/D-02):
 *   bannerVisible + onLine=false → "No network — trying to reconnect…"
 *   bannerVisible + onLine=true  → "Can't reach GRUVAX — trying to reconnect…"
 *
 * Nordic Grid design contract:
 * - Background: --gruvax-blue (reversed/urgent treatment — distinct from yellow StalenessBar)
 * - Text: --gruvax-white (blue-ground inverted)
 * - Icon: inline SVG connectivity icon, aria-hidden="true"
 * - role="alert" + aria-live="polite"
 * - NOT dismissible — clears on reconnect (D-04)
 * - Top-priority: suppresses other banners/pills while visible (D-04)
 *
 * ENFORCEMENT: no hardcoded hex — consume tokens only.
 */

import { useEffect, useState } from 'react'
import { useGruvaxStore } from '../../state/store'
import './OfflineBanner.css'

export function OfflineBanner() {
  // offline-confirmed: true only when was-connected-then-lost (gap-closure 09-05)
  const bannerVisible = useGruvaxStore((s) => s.connectivity.bannerVisible)
  const [isOnline, setIsOnline] = useState(navigator.onLine)

  useEffect(() => {
    const handleOnline = () => setIsOnline(true)
    const handleOffline = () => setIsOnline(false)
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  // Hidden unless offline-confirmed — never shows on bootstrap or auth-rejected state (PITFALLS 35)
  if (!bannerVisible) return null

  // Select copy by navigator.onLine as cosmetic secondary hint only (D-01/D-02)
  const copy = isOnline
    ? "Can't reach GRUVAX — trying to reconnect…"
    : 'No network — trying to reconnect…'

  return (
    <div
      className="offline-banner"
      role="alert"
      aria-live="polite"
    >
      {/* WifiOff inline SVG — aria-hidden="true" per StalenessBar pattern */}
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
        <line x1="1" y1="1" x2="23" y2="23" />
        <path d="M16.72 11.06A10.94 10.94 0 0 1 19 12.55" />
        <path d="M5 12.55a10.94 10.94 0 0 1 5.17-2.39" />
        <path d="M10.71 5.05A16 16 0 0 1 22.56 9" />
        <path d="M1.42 9a15.91 15.91 0 0 1 4.7-2.88" />
        <path d="M8.53 16.11a6 6 0 0 1 6.95 0" />
        <line x1="12" y1="20" x2="12.01" y2="20" />
      </svg>
      {copy}
    </div>
  )
}

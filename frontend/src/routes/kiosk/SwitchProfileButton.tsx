/**
 * SwitchProfileButton — persistent kiosk corner button (Surface 6, D2-09).
 *
 * Fixed bottom-right pill: Lucide RefreshCw 14px + "SWITCH" label.
 * Visible only when sessionStore.profileCount >= 2 (no-op on single-profile).
 * Opens SwitchProfileConfirm modal on tap.
 *
 * Design tokens only — no hardcoded hex.
 */

import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { useSessionStore } from '../../state/sessionStore'
import { SwitchProfileConfirm } from './SwitchProfileConfirm'

export function SwitchProfileButton() {
  const profileCount = useSessionStore((s) => s.profileCount)
  const [showConfirm, setShowConfirm] = useState(false)

  // Only render when 2+ profiles exist (D2-09 — hidden on single-profile deployment)
  if (profileCount < 2) return null

  return (
    <>
      <button
        type="button"
        className="switch-profile-btn"
        onClick={() => setShowConfirm(true)}
        aria-label="Switch profile"
      >
        <RefreshCw size={14} aria-hidden="true" />
        <span>SWITCH</span>
      </button>

      {showConfirm && (
        <SwitchProfileConfirm
          onCancel={() => setShowConfirm(false)}
        />
      )}
    </>
  )
}

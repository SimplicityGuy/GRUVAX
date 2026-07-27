/**
 * SwitchProfileButton — persistent kiosk corner button (Surface 6, D2-09).
 *
 * Fixed bottom-right pill: Lucide RefreshCw 14px + "SWITCH" label.
 * Visible only when sessionStore.profileCount >= 2 (no-op on single-profile)
 * AND the screen is not a PAIRED device (gruvax-ocrn).
 * Opens SwitchProfileConfirm modal on tap.
 *
 * gruvax-ocrn — why paired devices must not see this button:
 *   The confirm flow is unbindProfile() -> DELETE /api/session/bind, which clears
 *   only the BROWSE cookie; nothing in the flow touches gruvax.devices. Since a
 *   device binding OVERRIDES the browse cookie (D3-05, mirrored in deps.py's
 *   resolve_profile_from_request), a paired kiosk that "switched" to profile B was
 *   handed profile A right back — instantly, because ProfilePickerCard re-fetches
 *   /api/session after binding and that response still carries
 *   bound_profile_id = A. The user saw BINDING…, then A's collection, with no
 *   error anywhere, and could loop forever.
 *
 *   Hiding the affordance is the honest fix: re-pointing a paired device is an
 *   admin operation (PATCH /api/admin/devices/{id}, the DeviceDrawer reassign
 *   flow) because it is the only path that actually NULLs/repoints
 *   devices.profile_id. Making switch work for a paired device without a PIN is a
 *   product decision, not a bug fix. App.tsx already treats /select as off-limits
 *   for paired devices (it bounces them to '/' on reload), so this brings the
 *   button in line with routing that was already there.
 *
 * Design tokens only — no hardcoded hex.
 */

import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { useSessionStore } from '../../state/sessionStore'
import { SwitchProfileConfirm } from './SwitchProfileConfirm'

export function SwitchProfileButton() {
  const profileCount = useSessionStore((s) => s.profileCount)
  const isDevicePaired = useSessionStore((s) => s.isDevicePaired)
  const [showConfirm, setShowConfirm] = useState(false)

  // Only render when 2+ profiles exist (D2-09 — hidden on single-profile deployment)
  if (profileCount < 2) return null

  // gruvax-ocrn: on a paired device the switch flow is a silent no-op — the device
  // binding wins over the browse cookie the flow clears. Offer nothing rather than
  // a control that appears to work and doesn't.
  if (isDevicePaired) return null

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

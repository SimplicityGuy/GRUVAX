/**
 * ProfilePicker — /select route (D2-07).
 *
 * Shown when a browser session has no bound profile_id:
 *   - 0 profiles → OnboardingScreen
 *   - 2+ profiles → card grid (Surface 4)
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md).
 * No PIN required (R7 — open profile picker on LAN).
 */

import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { OnboardingScreen } from './OnboardingScreen'
import { ProfilePickerCard } from './ProfilePickerCard'
import type { SessionData } from '../api/session'
import './picker.css'
import './admin/admin.css'

export function ProfilePicker() {
  const navigate = useNavigate()
  const { data: session, isLoading, isError } = useQuery<SessionData>({
    queryKey: ['session'],
    queryFn: () => fetch('/api/session').then((r) => r.json() as Promise<SessionData>),
    staleTime: 0,   // always fresh on /select mount
  })

  // gruvax-ocrn: /select cannot do anything for a PAIRED device. Picking a card
  // there binds the browse cookie, but the device binding overrides it (D3-05), so
  // the kiosk reverts to its paired profile with no error — a silent no-op the user
  // can repeat forever. App.tsx already bounces paired devices off /select on
  // reload; do the same for an in-session arrival (deep link, back button, or any
  // future caller) so there is exactly one rule. Re-pointing a device stays an
  // admin operation (DeviceDrawer reassign).
  const pairedElsewhere = session?.is_device_paired === true && !!session.bound_profile_id
  useEffect(() => {
    if (pairedElsewhere) void navigate('/', { replace: true })
  }, [pairedElsewhere, navigate])

  if (isLoading) {
    return (
      <div className="picker-page" aria-busy="true">
        <div className="picker-loading" aria-label="Loading profiles…" />
      </div>
    )
  }

  if (isError || !session) {
    return (
      <div className="picker-page">
        <p className="picker-error" role="alert">
          Could not load profiles. Check your connection and refresh.
        </p>
      </div>
    )
  }

  if (session.profile_count === 0) {
    return <OnboardingScreen />
  }

  return (
    <div className="picker-page">
      <h1 className="picker-heading">CHOOSE A COLLECTION</h1>
      <div className="picker-grid" role="list">
        {session.profiles.map((profile) => (
          <ProfilePickerCard key={profile.id} profile={profile} />
        ))}
      </div>
      {/* D3-02: PAIR THIS SCREEN affordance — below the profile list */}
      <div style={{ marginTop: 'var(--gruvax-space-5)', width: '100%', maxWidth: '480px' }}>
        <button
          type="button"
          className="pair-screen-btn"
          onClick={() => void navigate('/pair')}
        >
          PAIR THIS SCREEN AS A DEVICE
        </button>
      </div>
    </div>
  )
}

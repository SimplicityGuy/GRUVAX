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

import { useQuery } from '@tanstack/react-query'
import { OnboardingScreen } from './OnboardingScreen'
import { ProfilePickerCard } from './ProfilePickerCard'
import type { SessionData } from '../api/session'
import './picker.css'

export function ProfilePicker() {
  const { data: session, isLoading, isError } = useQuery<SessionData>({
    queryKey: ['session'],
    queryFn: () => fetch('/api/session').then((r) => r.json() as Promise<SessionData>),
    staleTime: 0,   // always fresh on /select mount
  })

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
    </div>
  )
}

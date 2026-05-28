/**
 * ProfilePickerCard — individual card in the /select picker grid (Surface 4).
 *
 * onClick → bindProfile(id) → navigate('/', { replace: true }).
 * Shows "BINDING…" aria-busy state while the bind call is in flight.
 * No confirm — selection is non-destructive and reversible via Switch button.
 *
 * Design tokens only — no hardcoded hex.
 * XSS: all strings via JSX interpolation, never innerHTML (T-02-06-03).
 */

import { useState } from 'react'
import { useNavigate } from 'react-router'
import { bindProfile, type ProfileSummary } from '../api/session'
import { useSessionStore } from '../state/sessionStore'

/** Format last_sync_at as "today", "Nd ago", or "Not yet synced". */
function formatLastSync(lastSyncAt: string | null): string {
  if (!lastSyncAt) return 'Not yet synced'
  const syncDate = new Date(lastSyncAt)
  const now = new Date()
  const diffMs = now.getTime() - syncDate.getTime()
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))
  if (diffDays === 0) return 'Last sync: today'
  return `Last sync: ${diffDays}d ago`
}

/** Format item count with comma-thousands: "3,142 records" or "— records" */
function formatCount(count: number | null): string {
  if (count == null) return '— records'
  return `${count.toLocaleString()} records`
}

interface ProfilePickerCardProps {
  profile: ProfileSummary
}

export function ProfilePickerCard({ profile }: ProfilePickerCardProps) {
  const navigate = useNavigate()
  const setSession = useSessionStore((s) => s.setSession)
  const [isBinding, setIsBinding] = useState(false)
  const [bindError, setBindError] = useState<string | null>(null)

  const handleSelect = async () => {
    if (isBinding) return
    setIsBinding(true)
    setBindError(null)
    try {
      await bindProfile(profile.id)
      // Refresh session store with updated bound_profile_id from server.
      // Fetch fresh session data so the store reflects the new binding.
      const res = await fetch('/api/session')
      if (res.ok) {
        const data = await res.json()
        setSession(data)
      }
      void navigate('/', { replace: true })
    } catch {
      setBindError('Could not select this collection. Try again.')
      setIsBinding(false)
    }
  }

  return (
    <div
      role="listitem"
      className="picker-card"
      tabIndex={0}
      aria-label={`Choose ${profile.display_name} collection`}
      aria-busy={isBinding || undefined}
      onClick={() => { void handleSelect() }}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          void handleSelect()
        }
      }}
    >
      <span className="picker-card__name">{profile.display_name.toUpperCase()}</span>
      <span className="picker-card__count">{formatCount(profile.last_sync_item_count)}</span>
      <span className="picker-card__sync">{formatLastSync(profile.last_sync_at)}</span>
      {isBinding && (
        <span className="picker-card__binding" aria-live="polite">
          BINDING…
        </span>
      )}
      {bindError && (
        <span className="picker-card__error" role="alert">
          {bindError}
        </span>
      )}
    </div>
  )
}

/**
 * ProfileCard — a single profile row in the admin profile list.
 *
 * Displays: profile name (Barlow Condensed 900 24px), metadata line
 * ("Last sync: Nd ago · N,### records"), and a status badge.
 *
 * Metadata format strings (UI-SPEC §Surface 1):
 *   - Last sync: never → "Not yet synced"
 *   - Last sync: today → "Last sync: today"
 *   - Last sync: N days ago → "Last sync: Nd ago"
 *   - Combined: "Last sync: 3d ago · 3,142 records"
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 */

import type { AdminProfile } from '../../api/types'
import { ProfileStatusBadge } from './ProfileStatusBadge'
import type { ProfileStatus } from './ProfileStatusBadge'

interface ProfileCardProps {
  profile: AdminProfile
  onClick: () => void
  index: number
}

function formatLastSync(lastSyncAt: string | null | undefined): string {
  if (!lastSyncAt) return 'Not yet synced'

  const syncDate = new Date(lastSyncAt)
  const nowMs = Date.now()
  const diffMs = nowMs - syncDate.getTime()
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffDays === 0) return 'Last sync: today'
  return `Last sync: ${diffDays}d ago`
}

function formatItemCount(count: number | null | undefined): string | null {
  if (count == null) return null
  return `${count.toLocaleString('en-US')} records`
}

export function ProfileCard({ profile, onClick, index }: ProfileCardProps) {
  const syncText = formatLastSync(profile.last_sync_at)
  const countText = formatItemCount(profile.last_sync_item_count)

  const metaText = countText
    ? `${syncText} · ${countText}`
    : syncText

  // Even cards use off-white, odd use white
  const isEven = index % 2 === 0

  return (
    <button
      type="button"
      className={`profile-card${isEven ? ' profile-card--even' : ''}`}
      onClick={onClick}
      aria-label={`Edit profile ${profile.display_name}`}
    >
      <div className="profile-card-main">
        <span className="profile-card-name">
          {profile.display_name}
        </span>
        <ProfileStatusBadge status={profile.status as ProfileStatus} />
      </div>
      <p className="profile-card-meta">
        <span className="profile-card-meta-sync">{syncText}</span>
        {countText && (
          <>
            <span className="profile-card-meta-sep" aria-hidden="true"> · </span>
            <span className="profile-card-meta-count">{countText}</span>
          </>
        )}
      </p>
    </button>
  )
}

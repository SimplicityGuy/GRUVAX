/**
 * DeviceCard — a single device row in the admin device list.
 *
 * Displays: device name (Barlow Condensed 900 24px), state badge,
 * and a metadata line: "device: {id8} · {profile_name} · {last_seen}".
 * PENDING devices omit the profile name segment per 03-UI-SPEC.md.
 *
 * Last-seen formatting (03-UI-SPEC.md Surface 2):
 *   ≤ 2 minutes: "just now"
 *   3–59 minutes: "Nm ago"
 *   1–23 hours: "Nh ago"
 *   ≥ 24 hours: "Nd ago"
 *   Never seen: "never"
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 */

import { ChevronRight } from 'lucide-react'
import type { DeviceRow } from '../../api/devices'
import { DeviceStateBadge } from './DeviceStateBadge'

interface DeviceCardProps {
  device: DeviceRow
  onClick: () => void
  index: number
}

function formatLastSeen(lastSeenAt: string | null | undefined): string {
  if (!lastSeenAt) return 'never'
  const diffMs = Date.now() - new Date(lastSeenAt).getTime()
  const minutes = Math.floor(diffMs / 60_000)
  if (minutes <= 2) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

export function DeviceCard({ device, onClick, index }: DeviceCardProps) {
  const isEven = index % 2 === 0
  const id8 = device.id.replace(/-/g, '').slice(0, 8)
  const lastSeen = formatLastSeen(device.last_seen_at)

  return (
    <button
      type="button"
      className={`device-card${isEven ? ' device-card--even' : ''}`}
      onClick={onClick}
      aria-label={`Edit device ${device.display_name}`}
    >
      <div className="device-card-main">
        <span className="device-card-name">
          {device.display_name}
        </span>
        <div className="device-card-right">
          <DeviceStateBadge state={device.state} />
          <ChevronRight size={16} className="device-card-chevron" aria-hidden="true" />
        </div>
      </div>
      <p className="device-card-meta">
        <span className="device-card-meta-id">device: {id8}</span>
        {device.state !== 'pending' && device.profile_name && (
          <>
            <span className="device-card-meta-sep" aria-hidden="true"> · </span>
            <span className="device-card-meta-profile">{device.profile_name}</span>
          </>
        )}
        <span className="device-card-meta-sep" aria-hidden="true"> · </span>
        <span className="device-card-meta-seen">{lastSeen}</span>
      </p>
    </button>
  )
}

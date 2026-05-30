/**
 * ProfileDiagnosticsCard — per-profile sync diagnostics card (Phase 4 / D4-15).
 *
 * Renders one card per non-deleted profile in the PROFILES section of /admin/diagnostics.
 *
 * UI-SPEC Surface 1 layout:
 *   - Header row: profile name (Barlow Condensed 16px 700 --gruvax-blue) + ProfileStatusBadge
 *   - LAST SYNC: DM Mono 14px relative time ("3h ago" / "Never synced")
 *   - STATUS: ok/stale/outdated badge (diag-badge--{ok|stale|outdated})
 *   - ITEMS: DM Mono 14px comma-formatted count or "—"
 *   - LAST ERROR: Space Grotesk 14px muted, truncated 60 chars or "none"
 *
 * Focal point: ProfileStatusBadge (the first thing an admin scans).
 * No yellow on this card (§Color — yellow reserved for kiosk banner + spinner ring).
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 */

import type { ProfileDiagnosticEntry } from '../../api/adminClient'
import { ProfileStatusBadge } from './ProfileStatusBadge'
import type { ProfileStatus } from './ProfileStatusBadge'
import { formatIsoRelativeTime, stalenessStatusFromIso } from '../../lib/time'

interface ProfileDiagnosticsCardProps {
  profile: ProfileDiagnosticEntry
}

function deriveProfileStatus(profile: ProfileDiagnosticEntry): ProfileStatus {
  if (profile.app_token_revoked) return 're-auth-required'
  if (profile.last_sync_status === 'in_progress') return 'syncing'
  if (profile.last_sync_status === 'ok') return 'connected'
  if (profile.last_sync_status === 'failed') return 'connected' // connected but last sync failed
  // No sync yet
  return 'pending'
}

export function ProfileDiagnosticsCard({ profile }: ProfileDiagnosticsCardProps) {
  const profileStatus = deriveProfileStatus(profile)
  const stalenessClass = stalenessStatusFromIso(profile.last_sync_at)
  const lastSyncLabel = formatIsoRelativeTime(profile.last_sync_at)
  const itemsLabel =
    profile.last_sync_item_count != null
      ? profile.last_sync_item_count.toLocaleString('en-US')
      : '—'
  const errorLabel =
    profile.last_sync_error != null
      ? profile.last_sync_error.slice(0, 60) + (profile.last_sync_error.length > 60 ? '…' : '')
      : 'none'

  return (
    <div className="diag-profile-card">
      {/* Card header: profile name + status badge (focal point) */}
      <div className="diag-profile-card-header">
        <span className="diag-profile-name">{profile.display_name.toUpperCase()}</span>
        <ProfileStatusBadge status={profileStatus} />
      </div>

      {/* LAST SYNC row */}
      <div className="diag-status-row">
        <div className="diag-status-left">
          <span className="diag-row-label">LAST SYNC</span>
        </div>
        <span className="diag-cell-mono">{lastSyncLabel}</span>
      </div>

      {/* STATUS row */}
      <div className="diag-status-row">
        <div className="diag-status-left">
          <span className="diag-row-label">STATUS</span>
        </div>
        <span className={`diag-badge diag-badge--${stalenessClass}`} aria-label={`Sync status: ${stalenessClass}`}>
          {stalenessClass === 'ok' ? 'OK' : stalenessClass === 'stale' ? 'STALE' : 'OUTDATED'}
        </span>
      </div>

      {/* ITEMS row */}
      <div className="diag-status-row">
        <div className="diag-status-left">
          <span className="diag-row-label">ITEMS</span>
        </div>
        <span className="diag-cell-mono">{itemsLabel}</span>
      </div>

      {/* LAST ERROR row */}
      <div className="diag-status-row">
        <div className="diag-status-left">
          <span className="diag-row-label">LAST ERROR</span>
        </div>
        <span className="diag-cell-muted diag-profile-error">{errorLabel}</span>
      </div>
    </div>
  )
}

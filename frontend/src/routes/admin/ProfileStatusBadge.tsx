/**
 * ProfileStatusBadge — status pill for profile cards and the drawer.
 *
 * Four statuses: connected | pending | syncing | re-auth-required
 *
 * Badge tints are token-derived via color-mix (no hardcoded hex/rgba):
 *   - connected:  color-mix(in srgb, var(--gruvax-success) 12%, transparent)
 *   - pending:    color-mix(in srgb, var(--gruvax-warning) 12%, transparent)
 *   - syncing:    var(--gruvax-blue-faint) — existing token
 *   - re-auth:    color-mix(in srgb, var(--gruvax-error) 10%, transparent)
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 */

export type ProfileStatus =
  | 'connected'
  | 'pending'
  | 'syncing'
  | 're-auth-required'

interface ProfileStatusBadgeProps {
  status: ProfileStatus
}

const STATUS_LABELS: Record<ProfileStatus, string> = {
  connected: 'CONNECTED',
  pending: 'PENDING',
  syncing: 'SYNCING',
  're-auth-required': 'RE-AUTH REQUIRED',
}

export function ProfileStatusBadge({ status }: ProfileStatusBadgeProps) {
  const label = STATUS_LABELS[status]

  return (
    <span
      className={`profile-status-badge profile-status-badge--${status}`}
      aria-label={`Status: ${label}`}
    >
      {label}
    </span>
  )
}

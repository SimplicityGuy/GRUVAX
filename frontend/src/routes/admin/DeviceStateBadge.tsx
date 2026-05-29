/**
 * DeviceStateBadge — state pill for device cards and the drawer.
 *
 * Three states: paired | pending | revoked
 *
 * Badge tints are token-derived via color-mix (no hardcoded hex/rgba):
 *   - paired:  color-mix(in srgb, var(--gruvax-success) 12%, transparent)
 *   - pending: color-mix(in srgb, var(--gruvax-warning) 12%, transparent)
 *   - revoked: color-mix(in srgb, var(--gruvax-error) 10%, transparent)
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 * Follows the ProfileStatusBadge color-mix pattern (03-UI-SPEC.md Surface 2).
 */

export type DeviceState = 'paired' | 'pending' | 'revoked'

interface DeviceStateBadgeProps {
  state: DeviceState
}

const STATE_LABELS: Record<DeviceState, string> = {
  paired: 'PAIRED',
  pending: 'PENDING',
  revoked: 'REVOKED',
}

export function DeviceStateBadge({ state }: DeviceStateBadgeProps) {
  const label = STATE_LABELS[state]

  return (
    <span
      className={`device-state-badge device-state-badge--${state}`}
      aria-label={`Status: ${label}`}
    >
      {label}
    </span>
  )
}

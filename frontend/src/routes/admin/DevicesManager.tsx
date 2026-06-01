/**
 * DevicesManager — admin list of devices at /admin/devices.
 *
 * Shows grouped device cards (PAIRED → PENDING → REVOKED) + "ADD DEVICE" dashed row.
 * Tapping a card opens the DeviceDrawer bottom sheet.
 * Empty groups are omitted; all groups empty → "NO DEVICES YET" empty state.
 *
 * Group ordering per 03-UI-SPEC.md: PAIRED first (active devices),
 * then PENDING (awaiting assignment), then REVOKED (historical).
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 */

import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'
import { getAdminDevices } from '../../api/devices'
import type { DeviceRow } from '../../api/devices'
import { DeviceCard } from './DeviceCard'
import { DeviceDrawer } from './DeviceDrawer'
import { SyncToast } from '../../components/SyncToast'

type DrawerTarget = DeviceRow | 'bind' | null

export function DevicesManager() {
  const queryClient = useQueryClient()
  const [drawerTarget, setDrawerTarget] = useState<DrawerTarget>(null)
  const [prefillCode, setPrefillCode] = useState<string | undefined>(undefined)
  const [actionToast, setActionToast] = useState<{ message: string } | null>(null)
  const [searchParams, setSearchParams] = useSearchParams()

  // DEV-04: Read ?code= on mount; open bind drawer pre-filled; strip param to
  // prevent re-opening on reload (PinOverlay is a modal overlay so URL survives the PIN gate).
  useEffect(() => {
    const code = searchParams.get('code')
    if (code) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- reading external URL state on mount; canonical pattern for one-shot URL-param consumption
      setPrefillCode(code)
      setDrawerTarget('bind')
      // Strip the code param so a hard reload doesn't re-open the drawer
      const next = new URLSearchParams(searchParams)
      next.delete('code')
      setSearchParams(next, { replace: true })
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const { data: devices, isLoading, isError } = useQuery({
    queryKey: ['admin', 'devices'],
    queryFn: getAdminDevices,
    staleTime: 30_000,
  })

  function handleCardClick(device: DeviceRow) {
    setDrawerTarget(device)
  }

  function handleDrawerClose() {
    setDrawerTarget(null)
    setPrefillCode(undefined)
  }

  function handleActionComplete(message: string) {
    setActionToast({ message })
    void queryClient.invalidateQueries({ queryKey: ['admin', 'devices'] })
  }

  if (isLoading) {
    return (
      <div className="devices-manager-loading" aria-live="polite">
        Loading devices…
      </div>
    )
  }

  if (isError) {
    return (
      <div className="devices-manager-error" role="alert">
        Failed to load devices. Please try again.
      </div>
    )
  }

  const paired = devices?.paired ?? []
  const pending = devices?.pending ?? []
  const revoked = devices?.revoked ?? []
  const allEmpty = paired.length === 0 && pending.length === 0 && revoked.length === 0

  // Groups to render (only non-empty groups)
  const groups: Array<{ label: string; items: DeviceRow[] }> = [
    { label: 'PAIRED', items: paired },
    { label: 'PENDING', items: pending },
    { label: 'REVOKED', items: revoked },
  ].filter((g) => g.items.length > 0)

  return (
    <div className="devices-manager">
      <h1 className="devices-manager-heading">DEVICES</h1>

      {allEmpty ? (
        <div className="devices-empty-state">
          <p className="devices-empty-heading">NO DEVICES YET</p>
          <p className="devices-empty-body">
            Pair a kiosk screen to get started. Tap ADD DEVICE and enter the code shown on the kiosk.
          </p>
        </div>
      ) : (
        groups.map(({ label, items }) => (
          <div key={label} className="devices-group">
            <div className="devices-group-header">
              <span className="devices-group-label">{label}</span>
              <span className="devices-group-rule" aria-hidden="true" />
            </div>
            <ul className="devices-list" aria-label={`${label} device list`}>
              {items.map((device, index) => (
                <li key={device.id} className="devices-list-item">
                  <DeviceCard
                    device={device}
                    onClick={() => handleCardClick(device)}
                    index={index}
                  />
                </li>
              ))}
            </ul>
          </div>
        ))
      )}

      <button
        type="button"
        className="devices-add-row"
        onClick={() => setDrawerTarget('bind')}
        aria-label="Add a new device"
      >
        + ADD DEVICE
      </button>

      {drawerTarget !== null && (
        <DeviceDrawer
          device={drawerTarget === 'bind' ? undefined : drawerTarget}
          mode={drawerTarget === 'bind' ? 'bind' : 'view'}
          prefillCode={drawerTarget === 'bind' ? prefillCode : undefined}
          onClose={handleDrawerClose}
          onActionComplete={handleActionComplete}
        />
      )}

      {actionToast && (
        <SyncToast
          message={actionToast.message}
          onDismiss={() => setActionToast(null)}
        />
      )}
    </div>
  )
}

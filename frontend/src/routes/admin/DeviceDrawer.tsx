/**
 * DeviceDrawer — per-device bottom-sheet stub.
 *
 * STUB: This is a minimal placeholder so DeviceDrawer.test.tsx can import and
 * render the component while DeviceDrawer.test.tsx tests run RED on assertions.
 *
 * Plan 03-04 replaces this stub with the real implementation (analog: ProfileDrawer.tsx):
 *   - Sheet markup (sheet-scrim + record-picker-sheet + sheet-drag-pill + sheet-body)
 *   - bind mode: NumericKeypad with auto-submit on 4th digit
 *   - view mode: rename / change-profile / unbind / revoke actions
 *   - revoke-confirm / unbind-confirm destructive confirm dialogs
 *   - SSE subscription for device_revoked / device_reassigned events
 *   - Nordic Grid design tokens
 *
 * Props mirror ProfileDrawer.tsx shape (D3-02 reuse contract):
 *   device   — the device row to act on (undefined in bind/ADD-DEVICE mode)
 *   mode     — initial drawer mode ('bind' | 'view'), defaults to 'view'
 *   onClose  — called when the sheet dismisses
 */

interface DeviceDrawerProps {
  device?: unknown
  mode?: string
  onClose?: () => void
}

export function DeviceDrawer(_props: DeviceDrawerProps) {
  return null
}

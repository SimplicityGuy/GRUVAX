/**
 * DeviceDrawer — per-device bottom-sheet for all device lifecycle actions.
 *
 * Reuses the RecordPickerSheet markup verbatim:
 *   sheet-scrim + record-picker-sheet + sheet-drag-pill + sheet-body +
 *   sheet-heading + sheet-error + sheet-actions + focus trap (sheetRef).
 *
 * Drawer modes:
 *   'bind-code'      — ADD DEVICE flow: NumericKeypad, auto-submit on 4th digit
 *   'view'           — Context-sensitive action buttons by device state
 *   'rename'         — Inline text input for display name
 *   'pick-profile'   — Profile-picker list (used by BIND TO PROFILE + CHANGE PROFILE)
 *   'revoke-confirm' — Destructive inline confirmation for REVOKE
 *   'delete-confirm' — Destructive inline confirmation for DELETE PERMANENTLY
 *   'unbind-confirm' — Single inline confirmation for UNBIND
 *
 * Action sets by device state (03-UI-SPEC.md §Device Drawer):
 *   PENDING: BIND TO PROFILE, RENAME DEVICE, REVOKE DEVICE
 *   PAIRED:  RENAME DEVICE, CHANGE PROFILE, UNBIND, REVOKE DEVICE
 *   REVOKED: REINSTATE DEVICE, DELETE PERMANENTLY
 *
 * Profile picker (pick-profile mode):
 *   - Lists active profiles via getAdminProfiles() + TanStack Query
 *   - PENDING device: binds last pending code to chosen profile; falls back to
 *     code-entry (bind-code) when no pending code is available on the DeviceRow.
 *   - PAIRED device: PATCHes profile_id via changeDeviceProfile().
 *
 * NumericKeypad auto-submit: mirrors PinOverlay.tsx auto-submit-on-4th-digit pattern.
 *
 * Copywriting: all labels and error messages from 03-UI-SPEC.md Copywriting Contract.
 * Icons: Unplug (revoke), RefreshCcw (reinstate) per 03-UI-SPEC.md.
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { RefreshCcw, Unplug } from 'lucide-react'
import type { DeviceRow } from '../../api/devices'
import {
  bindDevice,
  changeDeviceProfile,
  deleteDevice,
  reinstateDevice,
  renameDevice,
  revokeDevice,
  unbindDevice,
} from '../../api/devices'
import { getAdminProfiles } from '../../api/adminClient'
import { NumericKeypad } from './NumericKeypad'

export interface DeviceDrawerProps {
  device?: DeviceRow
  mode?: string
  prefillCode?: string
  onClose: () => void
  onActionComplete?: (message: string) => void
}

type DrawerMode =
  | 'bind-code'
  | 'view'
  | 'rename'
  | 'pick-profile'
  | 'revoke-confirm'
  | 'delete-confirm'
  | 'unbind-confirm'

/** Map bind error type to UI-SPEC copy. */
function mapBindError(type: string | undefined): string {
  switch (type) {
    case 'code_not_found':
      return "That code wasn't found. Check the kiosk screen and try again."
    case 'code_expired':
      return 'That code has expired. Ask the kiosk to generate a new one.'
    case 'rate_limited':
      return 'Too many attempts. Wait a moment and try again.'
    default:
      return 'Something went wrong. Try again in a moment.'
  }
}

export function DeviceDrawer({ device, mode: initialMode, prefillCode, onClose, onActionComplete }: DeviceDrawerProps) {
  const queryClient = useQueryClient()
  const sheetRef = useRef<HTMLDivElement>(null)
  const headingId = 'device-drawer-heading'

  const isBindMode = initialMode === 'bind' || !device
  const [drawerMode, setDrawerMode] = useState<DrawerMode>(isBindMode ? 'bind-code' : 'view')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  // Bind mode state — code digits (mirrors PinOverlay)
  const [codeDigits, setCodeDigits] = useState<string[]>([])

  // Prefill mode: true when prefillCode is set and user hasn't dismissed it.
  // Local state allows "Enter a different code" to drop back to NumericKeypad.
  const [usePrefill, setUsePrefill] = useState<boolean>(!!prefillCode)

  // Rename mode state
  const [nameValue, setNameValue] = useState(device?.display_name ?? '')

  // Profile-picker: track which context triggered the pick ('bind-to-profile' | 'change-profile')
  const [profilePickContext, setProfilePickContext] = useState<'bind-to-profile' | 'change-profile'>('change-profile')

  // Profiles query — fetched lazily when profile-picker is opened (staleTime: 30s)
  const { data: profiles, isLoading: profilesLoading } = useQuery({
    queryKey: ['admin', 'profiles'],
    queryFn: getAdminProfiles,
    enabled: drawerMode === 'pick-profile',
    staleTime: 30_000,
  })

  // Focus trap: focus first focusable element on mount
  useEffect(() => {
    const el = sheetRef.current
    if (!el) return
    const focusable = el.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    )
    if (focusable.length > 0) focusable[0].focus()
  }, [])

  // ── Bind via code ─────────────────────────────────────────────────────────
  const handleBind = useCallback(async (code: string) => {
    setSaveError(null)
    setIsSaving(true)
    try {
      const bound = await bindDevice({ code })
      void queryClient.invalidateQueries({ queryKey: ['admin', 'devices'] })
      onActionComplete?.(`Device "${bound.display_name}" paired successfully.`)
      onClose()
    } catch (err: unknown) {
      const anyErr = err as { detail?: { type?: string } }
      setSaveError(mapBindError(anyErr?.detail?.type))
      setCodeDigits([])
    } finally {
      setIsSaving(false)
    }
  }, [queryClient, onActionComplete, onClose])

  // ── Pick profile ───────────────────────────────────────────────────────────
  const handlePickProfile = useCallback(async (profileId: string) => {
    if (!device) return
    setSaveError(null)
    setIsSaving(true)
    try {
      if (profilePickContext === 'change-profile') {
        // PAIRED: PATCH profile_id
        await changeDeviceProfile(device.id, profileId)
        void queryClient.invalidateQueries({ queryKey: ['admin', 'devices'] })
        onActionComplete?.(`Profile updated for ${device.display_name}.`)
        onClose()
      } else {
        // PENDING: bind with last pending code if present, else fall back to code entry.
        // WR-04: The backend does not currently return last_pairing_code in DeviceRow, so
        // pendingCode will always be undefined and this fast-path is presently inert — the
        // code always falls through to the 'bind-code' mode below. This branch is preserved
        // for the planned bind-to-profile flow that will add the field to the API response.
        const pendingCode = (device as DeviceRow & { last_pairing_code?: string }).last_pairing_code
        if (pendingCode) {
          const bound = await bindDevice({ code: pendingCode, profile_id: profileId })
          void queryClient.invalidateQueries({ queryKey: ['admin', 'devices'] })
          onActionComplete?.(`Device "${bound.display_name}" paired successfully.`)
          onClose()
        } else {
          // No pending code available — fall back to manual code entry
          setDrawerMode('bind-code')
          setSaveError(null)
        }
      }
    } catch (err: unknown) {
      const anyErr = err as { detail?: { type?: string } }
      setSaveError(mapBindError(anyErr?.detail?.type))
    } finally {
      setIsSaving(false)
    }
  }, [device, profilePickContext, queryClient, onActionComplete, onClose])

  // NumericKeypad digit handler — auto-submit on 4th digit (mirrors PinOverlay.tsx)
  const handleCodeDigit = useCallback((d: string) => {
    if (isSaving) return
    if (codeDigits.length >= 4) return
    const next = [...codeDigits, d]
    setCodeDigits(next)
    if (next.length === 4) {
      void handleBind(next.join(''))
    }
  }, [codeDigits, isSaving, handleBind])

  const handleCodeBackspace = useCallback(() => {
    if (isSaving) return
    setCodeDigits((prev) => prev.slice(0, -1))
    setSaveError(null)
  }, [isSaving])

  // ── Rename ────────────────────────────────────────────────────────────────
  async function handleSaveName() {
    if (!device || !nameValue.trim()) return
    setSaveError(null)
    setIsSaving(true)
    try {
      await renameDevice(device.id, nameValue.trim())
      void queryClient.invalidateQueries({ queryKey: ['admin', 'devices'] })
      onActionComplete?.(`Device renamed to "${nameValue.trim()}".`)
      setDrawerMode('view')
    } catch {
      setSaveError('Something went wrong. Try again in a moment.')
    } finally {
      setIsSaving(false)
    }
  }

  // ── Unbind ────────────────────────────────────────────────────────────────
  async function handleUnbind() {
    if (!device) return
    setSaveError(null)
    setIsSaving(true)
    try {
      await unbindDevice(device.id)
      void queryClient.invalidateQueries({ queryKey: ['admin', 'devices'] })
      onActionComplete?.(`${device.display_name} unbound.`)
      onClose()
    } catch {
      setSaveError('Something went wrong. Try again in a moment.')
    } finally {
      setIsSaving(false)
    }
  }

  // ── Revoke ────────────────────────────────────────────────────────────────
  async function handleRevoke() {
    if (!device) return
    setSaveError(null)
    setIsSaving(true)
    try {
      await revokeDevice(device.id)
      void queryClient.invalidateQueries({ queryKey: ['admin', 'devices'] })
      onActionComplete?.(`${device.display_name} revoked.`)
      onClose()
    } catch {
      setSaveError('Something went wrong. Try again in a moment.')
    } finally {
      setIsSaving(false)
    }
  }

  // ── Reinstate ─────────────────────────────────────────────────────────────
  async function handleReinstate() {
    if (!device) return
    setSaveError(null)
    setIsSaving(true)
    try {
      await reinstateDevice(device.id)
      void queryClient.invalidateQueries({ queryKey: ['admin', 'devices'] })
      onActionComplete?.(`${device.display_name} reinstated.`)
      onClose()
    } catch {
      setSaveError('Something went wrong. Try again in a moment.')
    } finally {
      setIsSaving(false)
    }
  }

  // ── Delete ────────────────────────────────────────────────────────────────
  async function handleDelete() {
    if (!device) return
    setSaveError(null)
    setIsSaving(true)
    try {
      await deleteDevice(device.id)
      void queryClient.invalidateQueries({ queryKey: ['admin', 'devices'] })
      onActionComplete?.(`${device.display_name} deleted.`)
      onClose()
    } catch {
      setSaveError('Something went wrong. Try again in a moment.')
    } finally {
      setIsSaving(false)
    }
  }

  // ── Derived heading ───────────────────────────────────────────────────────
  const heading = drawerMode === 'bind-code'
    ? ((prefillCode && usePrefill) ? 'PAIR THIS DEVICE' : 'ENTER PAIRING CODE')
    : (device?.display_name.toUpperCase() ?? '')

  const id8 = device ? device.id.replace(/-/g, '').slice(0, 8) : null

  return (
    <>
      {/* Scrim */}
      <div
        className="sheet-scrim"
        aria-hidden="true"
        onClick={isSaving ? undefined : onClose}
      />

      {/* Bottom sheet */}
      <div
        ref={sheetRef}
        className="record-picker-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby={headingId}
      >
        {/* Drag pill */}
        <div className="sheet-drag-pill" aria-hidden="true" />

        <div className="sheet-body">
          <h2 id={headingId} className="sheet-heading">
            {heading}
          </h2>

          {/* Device ID line (view mode only) */}
          {device && drawerMode !== 'bind-code' && id8 && (
            <p className="device-id-line">ID: {id8}</p>
          )}

          {/* ── BIND-CODE mode: prefill confirm OR NumericKeypad ───────────── */}
          {drawerMode === 'bind-code' && prefillCode && usePrefill && (
            /* Prefill confirm screen (D-04: no auto-submit; explicit one-tap confirm) */
            <div className="device-prefill-confirm">
              <p className="device-prefill-instruction">
                Pair this device with your GRUVAX collection using code:
              </p>
              <p className="device-prefill-code">{prefillCode}</p>
            </div>
          )}

          {drawerMode === 'bind-code' && !(prefillCode && usePrefill) && (
            <>
              {/* 4-digit code display boxes */}
              <div className="device-drawer-code-display" aria-live="polite" aria-label={`Entered ${codeDigits.length} of 4 digits`}>
                {Array.from({ length: 4 }, (_, i) => (
                  <span
                    key={i}
                    className={`device-drawer-code-digit${i >= codeDigits.length ? ' device-drawer-code-digit--empty' : ''}`}
                  >
                    {codeDigits[i] ?? '·'}
                  </span>
                ))}
              </div>

              <NumericKeypad
                onDigit={handleCodeDigit}
                onBackspace={handleCodeBackspace}
                disabled={isSaving}
              />
            </>
          )}

          {/* ── RENAME mode: name input ───────────────────────────────────── */}
          {drawerMode === 'rename' && (
            <div className="profile-drawer-section">
              <label htmlFor="device-rename-input" className="profile-field-label">
                DEVICE NAME
              </label>
              <input
                id="device-rename-input"
                type="text"
                className="profile-field-input"
                value={nameValue}
                onChange={(e) => setNameValue(e.target.value)}
                placeholder={device?.display_name ?? ''}
                maxLength={64}
                disabled={isSaving}
                autoComplete="off"
              />
            </div>
          )}

          {/* ── REVOKE CONFIRM ───────────────────────────────────────────── */}
          {drawerMode === 'revoke-confirm' && (
            <div
              className="device-revoke-confirm"
              role="alertdialog"
              aria-labelledby="revoke-confirm-heading"
            >
              <h3 id="revoke-confirm-heading" className="device-confirm-heading">
                Revoke this device?
              </h3>
              <p className="device-confirm-body">
                The kiosk will be locked out immediately. It can be reinstated later.
              </p>
            </div>
          )}

          {/* ── DELETE CONFIRM ───────────────────────────────────────────── */}
          {drawerMode === 'delete-confirm' && (
            <div
              className="device-delete-confirm"
              role="alertdialog"
              aria-labelledby="delete-confirm-heading"
            >
              <h3 id="delete-confirm-heading" className="device-confirm-heading">
                Delete this device record?
              </h3>
              <p className="device-confirm-body">
                This removes the device history. The kiosk will need to pair again from scratch.
              </p>
            </div>
          )}

          {/* ── UNBIND CONFIRM ───────────────────────────────────────────── */}
          {drawerMode === 'unbind-confirm' && (
            <div
              className="device-unbind-confirm"
              role="alertdialog"
              aria-labelledby="unbind-confirm-heading"
            >
              <p id="unbind-confirm-heading" className="device-confirm-body">
                Remove the profile binding? The kiosk will return to the profile picker.
              </p>
            </div>
          )}

          {/* ── PROFILE PICKER ───────────────────────────────────────────── */}
          {drawerMode === 'pick-profile' && (
            <div className="device-profile-picker" aria-label="Select a profile">
              {profilesLoading && (
                <p className="device-profile-picker-loading">Loading profiles…</p>
              )}
              {!profilesLoading && profiles && profiles.length === 0 && (
                <p className="device-profile-picker-empty">No profiles available.</p>
              )}
              {!profilesLoading && profiles && profiles.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className="device-profile-picker-row"
                  onClick={() => void handlePickProfile(p.id)}
                  disabled={isSaving}
                  aria-pressed={device?.profile_id === p.id}
                >
                  <span className="device-profile-picker-name">{p.display_name.toUpperCase()}</span>
                  {device?.profile_id === p.id && (
                    <span className="device-profile-picker-current" aria-hidden="true">
                      CURRENT
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}

          {/* ── Error ────────────────────────────────────────────────────── */}
          {saveError && (
            <p className="sheet-error" role="alert">
              {saveError}
            </p>
          )}

          {/* ── Actions ──────────────────────────────────────────────────── */}
          <div className="sheet-actions">

            {/* ── BIND-CODE mode: prefill confirm CTA ── */}
            {drawerMode === 'bind-code' && prefillCode && usePrefill && (
              <>
                <button
                  type="button"
                  className="device-prefill-cta"
                  onClick={() => void handleBind(prefillCode)}
                  disabled={isSaving}
                  aria-busy={isSaving}
                  aria-label={`Pair this device using code ${prefillCode}`}
                >
                  {isSaving ? 'PAIRING…' : 'PAIR THIS DEVICE'}
                </button>
                <button
                  type="button"
                  className="device-prefill-different-code"
                  onClick={() => {
                    // Clear prefill state — parent manages prefillCode prop, so we
                    // signal "typed mode" by toggling to a local state override.
                    // Since prefillCode comes from props, we use an internal flag.
                    setSaveError(null)
                    setDrawerMode('bind-code')
                    // Force the view to typed-code mode by clearing prefill via parent or
                    // using the component-internal approach: pass undefined as local override.
                    // Because prefillCode is a prop, we use a local state to mask it.
                    setUsePrefill(false)
                  }}
                  disabled={isSaving}
                >
                  Enter a different code
                </button>
              </>
            )}

            {/* ── BIND-CODE mode: typed code ── */}
            {drawerMode === 'bind-code' && !(prefillCode && usePrefill) && (
              <button
                type="button"
                className="editor-btn-primary profile-btn-primary"
                onClick={() => codeDigits.length === 4 ? void handleBind(codeDigits.join('')) : undefined}
                disabled={isSaving || codeDigits.length < 4}
                aria-busy={isSaving}
              >
                {isSaving ? 'BINDING…' : 'BIND DEVICE'}
              </button>
            )}

            {/* ── PENDING actions ── */}
            {device?.state === 'pending' && drawerMode === 'view' && (
              <>
                <button
                  type="button"
                  className="profile-btn-secondary"
                  onClick={() => {
                    setProfilePickContext('bind-to-profile')
                    setDrawerMode('pick-profile')
                    setSaveError(null)
                  }}
                >
                  BIND TO PROFILE
                </button>
                <button
                  type="button"
                  className="profile-btn-secondary"
                  onClick={() => {
                    setNameValue(device.display_name)
                    setDrawerMode('rename')
                    setSaveError(null)
                  }}
                >
                  RENAME DEVICE
                </button>
                <button
                  type="button"
                  className="profile-btn-destructive"
                  onClick={() => setDrawerMode('revoke-confirm')}
                >
                  <Unplug size={16} aria-hidden="true" />
                  REVOKE DEVICE
                </button>
              </>
            )}

            {/* ── PAIRED actions ── */}
            {device?.state === 'paired' && drawerMode === 'view' && (
              <>
                <button
                  type="button"
                  className="profile-btn-secondary"
                  onClick={() => {
                    setNameValue(device.display_name)
                    setDrawerMode('rename')
                    setSaveError(null)
                  }}
                >
                  RENAME DEVICE
                </button>
                <button
                  type="button"
                  className="profile-btn-secondary"
                  onClick={() => {
                    setProfilePickContext('change-profile')
                    setDrawerMode('pick-profile')
                    setSaveError(null)
                  }}
                >
                  CHANGE PROFILE
                </button>
                <button
                  type="button"
                  className="profile-btn-tertiary"
                  onClick={() => setDrawerMode('unbind-confirm')}
                >
                  UNBIND
                </button>
                <button
                  type="button"
                  className="profile-btn-destructive"
                  onClick={() => setDrawerMode('revoke-confirm')}
                >
                  <Unplug size={16} aria-hidden="true" />
                  REVOKE DEVICE
                </button>
              </>
            )}

            {/* ── REVOKED actions ── */}
            {device?.state === 'revoked' && drawerMode === 'view' && (
              <>
                <button
                  type="button"
                  className="profile-btn-secondary"
                  onClick={() => void handleReinstate()}
                  disabled={isSaving}
                  aria-busy={isSaving}
                >
                  <RefreshCcw size={16} aria-hidden="true" />
                  {isSaving ? 'REINSTATING…' : 'REINSTATE DEVICE'}
                </button>
                <button
                  type="button"
                  className="profile-btn-destructive"
                  onClick={() => setDrawerMode('delete-confirm')}
                >
                  DELETE PERMANENTLY
                </button>
              </>
            )}

            {/* ── RENAME: SAVE NAME + back ── */}
            {drawerMode === 'rename' && (
              <>
                <button
                  type="button"
                  className="editor-btn-primary profile-btn-primary"
                  onClick={() => void handleSaveName()}
                  disabled={isSaving || !nameValue.trim()}
                  aria-busy={isSaving}
                >
                  {isSaving ? 'SAVING…' : 'SAVE NAME'}
                </button>
                <button
                  type="button"
                  className="sheet-cancel-btn"
                  onClick={() => { setDrawerMode('view'); setSaveError(null) }}
                  disabled={isSaving}
                >
                  CANCEL
                </button>
              </>
            )}

            {/* ── REVOKE CONFIRM: REVOKE + CANCEL ── */}
            {drawerMode === 'revoke-confirm' && (
              <>
                <button
                  type="button"
                  className="profile-btn-destructive"
                  style={{ background: 'var(--gruvax-error)', color: 'var(--gruvax-white)' }}
                  onClick={() => void handleRevoke()}
                  disabled={isSaving}
                  aria-busy={isSaving}
                >
                  {isSaving ? 'REVOKING…' : 'REVOKE'}
                </button>
                <button
                  type="button"
                  className="sheet-cancel-btn"
                  onClick={() => setDrawerMode('view')}
                  disabled={isSaving}
                >
                  CANCEL
                </button>
              </>
            )}

            {/* ── DELETE CONFIRM: DELETE + CANCEL ── */}
            {drawerMode === 'delete-confirm' && (
              <>
                <button
                  type="button"
                  className="profile-btn-destructive"
                  style={{ background: 'var(--gruvax-error)', color: 'var(--gruvax-white)' }}
                  onClick={() => void handleDelete()}
                  disabled={isSaving}
                  aria-busy={isSaving}
                >
                  {isSaving ? 'DELETING…' : 'DELETE'}
                </button>
                <button
                  type="button"
                  className="sheet-cancel-btn"
                  onClick={() => setDrawerMode('view')}
                  disabled={isSaving}
                >
                  CANCEL
                </button>
              </>
            )}

            {/* ── UNBIND CONFIRM: UNBIND + CANCEL ── */}
            {drawerMode === 'unbind-confirm' && (
              <>
                <button
                  type="button"
                  className="editor-btn-primary profile-btn-primary"
                  onClick={() => void handleUnbind()}
                  disabled={isSaving}
                  aria-busy={isSaving}
                >
                  {isSaving ? 'UNBINDING…' : 'UNBIND'}
                </button>
                <button
                  type="button"
                  className="sheet-cancel-btn"
                  onClick={() => setDrawerMode('view')}
                  disabled={isSaving}
                >
                  CANCEL
                </button>
              </>
            )}

            {/* ── PICK-PROFILE: BACK ── */}
            {drawerMode === 'pick-profile' && (
              <button
                type="button"
                className="sheet-cancel-btn"
                onClick={() => { setDrawerMode('view'); setSaveError(null) }}
                disabled={isSaving}
              >
                CANCEL
              </button>
            )}

            {/* ── CLOSE — shown in view mode and bind mode when no confirm active ── */}
            {(drawerMode === 'view' || drawerMode === 'bind-code') && (
              <button
                type="button"
                className="sheet-cancel-btn"
                onClick={onClose}
                disabled={isSaving}
              >
                CANCEL
              </button>
            )}
          </div>
        </div>
      </div>
    </>
  )
}

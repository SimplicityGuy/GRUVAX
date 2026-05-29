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
 *   'revoke-confirm' — Destructive inline confirmation for REVOKE
 *   'delete-confirm' — Destructive inline confirmation for DELETE PERMANENTLY
 *   'unbind-confirm' — Single inline confirmation for UNBIND
 *
 * Action sets by device state (03-UI-SPEC.md §Device Drawer):
 *   PENDING: BIND TO PROFILE, RENAME DEVICE, REVOKE DEVICE
 *   PAIRED:  RENAME DEVICE, CHANGE PROFILE, UNBIND, REVOKE DEVICE
 *   REVOKED: REINSTATE DEVICE, DELETE PERMANENTLY
 *
 * NumericKeypad auto-submit: mirrors PinOverlay.tsx auto-submit-on-4th-digit pattern.
 *
 * Copywriting: all labels and error messages from 03-UI-SPEC.md Copywriting Contract.
 * Icons: Unplug (revoke), RefreshCcw (reinstate) per 03-UI-SPEC.md.
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { RefreshCcw, Unplug } from 'lucide-react'
import type { DeviceRow } from '../../api/devices'
import {
  bindDevice,
  deleteDevice,
  reinstateDevice,
  renameDevice,
  revokeDevice,
  unbindDevice,
} from '../../api/devices'
import { NumericKeypad } from './NumericKeypad'

export interface DeviceDrawerProps {
  device?: DeviceRow
  mode?: string
  onClose: () => void
  onActionComplete?: (message: string) => void
}

type DrawerMode =
  | 'bind-code'
  | 'view'
  | 'rename'
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

export function DeviceDrawer({ device, mode: initialMode, onClose, onActionComplete }: DeviceDrawerProps) {
  const queryClient = useQueryClient()
  const sheetRef = useRef<HTMLDivElement>(null)
  const headingId = 'device-drawer-heading'

  const isBindMode = initialMode === 'bind' || !device
  const [drawerMode, setDrawerMode] = useState<DrawerMode>(isBindMode ? 'bind-code' : 'view')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  // Bind mode state — code digits (mirrors PinOverlay)
  const [codeDigits, setCodeDigits] = useState<string[]>([])

  // Rename mode state
  const [nameValue, setNameValue] = useState(device?.display_name ?? '')

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
    ? 'ENTER PAIRING CODE'
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

          {/* ── BIND-CODE mode: code display + NumericKeypad ─────────────── */}
          {drawerMode === 'bind-code' && (
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

          {/* ── Error ────────────────────────────────────────────────────── */}
          {saveError && (
            <p className="sheet-error" role="alert">
              {saveError}
            </p>
          )}

          {/* ── Actions ──────────────────────────────────────────────────── */}
          <div className="sheet-actions">

            {/* ── BIND-CODE mode ── */}
            {drawerMode === 'bind-code' && (
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

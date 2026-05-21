/**
 * Settings page — /admin/settings (UI-SPEC §G).
 *
 * Phase 3 scope:
 *   - Change PIN (current PIN + new 4-digit PIN)
 *   - Nominal cube capacity (integer ≥ 1, default 95)
 *   - Idle session timeout (5–30 minutes, default 10)
 *
 * LED settings (Phase 5) are deferred — D-18.
 */

import { useEffect, useState } from 'react'
import { changePin, getAdminSettings, putAdminSettings } from '../../api/adminClient'
import './admin.css'

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

export function Settings() {
  const [capacity, setCapacity] = useState(95)
  const [idleMin, setIdleMin] = useState(10)
  const [settingsStatus, setSettingsStatus] = useState<SaveStatus>('idle')
  const [settingsError, setSettingsError] = useState('')

  const [currentPin, setCurrentPin] = useState('')
  const [newPin, setNewPin] = useState('')
  const [pinStatus, setPinStatus] = useState<SaveStatus>('idle')
  const [pinError, setPinError] = useState('')

  // Load current settings on mount
  useEffect(() => {
    getAdminSettings()
      .then((s) => {
        setCapacity(s.nominal_capacity)
        setIdleMin(Math.round(s.idle_ttl_seconds / 60))
      })
      .catch(() => {/* proceed with defaults */})
  }, [])

  const handleSaveSettings = async () => {
    setSettingsStatus('saving')
    setSettingsError('')
    try {
      const updated = await putAdminSettings({
        nominal_capacity: capacity,
        idle_ttl_seconds: idleMin * 60,
      })
      setCapacity(updated.nominal_capacity)
      setIdleMin(Math.round(updated.idle_ttl_seconds / 60))
      setSettingsStatus('saved')
      setTimeout(() => setSettingsStatus('idle'), 2000)
    } catch {
      setSettingsStatus('error')
      setSettingsError('Failed to save settings. Please try again.')
    }
  }

  const handleChangePin = async () => {
    if (!currentPin || currentPin.length !== 4) {
      setPinError('Current PIN must be 4 digits')
      return
    }
    if (!newPin || newPin.length !== 4) {
      setPinError('New PIN must be 4 digits')
      return
    }
    setPinStatus('saving')
    setPinError('')
    try {
      await changePin({ current_pin: currentPin, new_pin: newPin })
      setPinStatus('saved')
      setCurrentPin('')
      setNewPin('')
      setTimeout(() => setPinStatus('idle'), 2000)
    } catch {
      setPinStatus('error')
      setPinError('Incorrect current PIN or save failed.')
    }
  }

  return (
    <div className="settings-page">

      {/* ── Change PIN ──────────────────────────────────────────────────────── */}
      <section className="settings-section" aria-labelledby="pin-heading">
        <h2 id="pin-heading" className="settings-heading">CHANGE PIN</h2>

        <div className="settings-field">
          <label className="settings-label" htmlFor="current-pin">
            CURRENT PIN
          </label>
          <input
            id="current-pin"
            type="password"
            inputMode="numeric"
            maxLength={4}
            pattern="[0-9]{4}"
            value={currentPin}
            onChange={(e) => setCurrentPin(e.target.value.replace(/\D/g, '').slice(0, 4))}
            placeholder="• • • •"
            className="settings-pin-input"
            autoComplete="current-password"
          />
        </div>

        <div className="settings-field">
          <label className="settings-label" htmlFor="new-pin">
            NEW PIN
          </label>
          <input
            id="new-pin"
            type="password"
            inputMode="numeric"
            maxLength={4}
            pattern="[0-9]{4}"
            value={newPin}
            onChange={(e) => setNewPin(e.target.value.replace(/\D/g, '').slice(0, 4))}
            placeholder="• • • •"
            className="settings-pin-input"
            autoComplete="new-password"
          />
        </div>

        {pinError && (
          <p className="settings-error" role="alert">{pinError}</p>
        )}

        {pinStatus === 'saved' && (
          <p className="settings-success" role="status">PIN updated successfully.</p>
        )}

        <button
          type="button"
          className="settings-btn-primary"
          onClick={() => { void handleChangePin() }}
          disabled={pinStatus === 'saving'}
        >
          {pinStatus === 'saving' ? 'SAVING…' : 'SAVE NEW PIN'}
        </button>
      </section>

      {/* ── Nominal capacity ────────────────────────────────────────────────── */}
      <section className="settings-section" aria-labelledby="capacity-heading">
        <h2 id="capacity-heading" className="settings-heading">CAPACITY & TIMEOUT</h2>

        <div className="settings-field">
          <label className="settings-label" htmlFor="nominal-capacity">
            NOMINAL CAPACITY (RECORDS PER CUBE)
          </label>
          <input
            id="nominal-capacity"
            type="number"
            min={1}
            max={999}
            value={capacity}
            onChange={(e) => setCapacity(Math.max(1, parseInt(e.target.value, 10) || 1))}
            className="settings-number-input"
          />
          <p className="settings-hint">
            Used for fill-level gauge. Typical Kallax holds 90–100 LPs.
          </p>
        </div>

        <div className="settings-field">
          <label className="settings-label" htmlFor="idle-timeout">
            SESSION IDLE TIMEOUT (MINUTES)
          </label>
          <input
            id="idle-timeout"
            type="number"
            min={5}
            max={30}
            value={idleMin}
            onChange={(e) =>
              setIdleMin(
                Math.min(30, Math.max(5, parseInt(e.target.value, 10) || 10)),
              )
            }
            className="settings-number-input"
          />
          <p className="settings-hint">
            Uncommitted edits are preserved — PIN is re-required after timeout.
          </p>
        </div>

        {settingsError && (
          <p className="settings-error" role="alert">{settingsError}</p>
        )}

        {settingsStatus === 'saved' && (
          <p className="settings-success" role="status">Settings saved.</p>
        )}

        <button
          type="button"
          className="settings-btn-primary"
          onClick={() => { void handleSaveSettings() }}
          disabled={settingsStatus === 'saving'}
        >
          {settingsStatus === 'saving' ? 'SAVING…' : 'SAVE SETTINGS'}
        </button>
      </section>
    </div>
  )
}

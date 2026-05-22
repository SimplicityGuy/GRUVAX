/**
 * Settings page — /admin/settings (UI-SPEC §G, §H).
 *
 * Phase 3 scope:
 *   - Change PIN (current PIN + new 4-digit PIN)
 *   - Nominal cube capacity (integer ≥ 1, default 95)
 *   - Idle session timeout (5–30 minutes, default 10)
 *
 * Phase 5 additions (UI-SPEC §H):
 *   - Segment override drift alert threshold (integer 1–20 percentage points, default 3)
 *   - REVIEW OVERRIDES secondary button
 *
 * LED settings are deferred.
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { changePin, getAdminSettings, putAdminSettings } from '../../api/adminClient'
import './admin.css'

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

export function Settings() {
  const navigate = useNavigate()
  const [capacity, setCapacity] = useState(95)
  const [idleMin, setIdleMin] = useState(10)
  const [settingsStatus, setSettingsStatus] = useState<SaveStatus>('idle')
  const [settingsError, setSettingsError] = useState('')

  const [currentPin, setCurrentPin] = useState('')
  const [newPin, setNewPin] = useState('')
  const [pinStatus, setPinStatus] = useState<SaveStatus>('idle')
  const [pinError, setPinError] = useState('')

  // Phase 5: drift threshold (UI-SPEC §H)
  const [driftThresholdPct, setDriftThresholdPct] = useState(3)
  const [driftStatus, setDriftStatus] = useState<SaveStatus>('idle')
  const [driftError, setDriftError] = useState('')

  // Load current settings on mount — use backend key names (WR-01)
  useEffect(() => {
    getAdminSettings()
      .then((s) => {
        setCapacity(s.cube_nominal_capacity)
        setIdleMin(Math.round(s.session_idle_ttl_seconds / 60))
      })
      .catch(() => {/* proceed with defaults */})
  }, [])

  const handleSaveSettings = async () => {
    setSettingsStatus('saving')
    setSettingsError('')
    try {
      const updated = await putAdminSettings({
        cube_nominal_capacity: capacity,
        session_idle_ttl_seconds: idleMin * 60,
      })
      // PUT returns {updated: [...]} not a settings object; re-fetch to confirm
      setCapacity(updated.cube_nominal_capacity ?? capacity)
      setIdleMin(Math.round((updated.session_idle_ttl_seconds ?? idleMin * 60) / 60))
      setSettingsStatus('saved')
      setTimeout(() => setSettingsStatus('idle'), 2000)
    } catch {
      setSettingsStatus('error')
      setSettingsError('Failed to save settings. Please try again.')
    }
  }

  // Phase 5: Save drift threshold (stored client-side via localStorage for now;
  // no backend endpoint yet — D-03 deferred to backend settings extension).
  const handleSaveDriftThreshold = async () => {
    setDriftStatus('saving')
    setDriftError('')
    try {
      localStorage.setItem('gruvax_drift_threshold_pct', String(driftThresholdPct))
      setDriftStatus('saved')
      setTimeout(() => setDriftStatus('idle'), 2000)
    } catch {
      setDriftStatus('error')
      setDriftError('Could not save drift threshold.')
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

      {/* ── Segment Overrides (Phase 5, UI-SPEC §H) ─────────────────────────── */}
      <section className="settings-section settings-section--overrides" aria-labelledby="overrides-heading">
        <h2 id="overrides-heading" className="settings-heading settings-heading--xl">
          SEGMENT OVERRIDES
        </h2>

        <div className="settings-field">
          <label className="settings-label" htmlFor="drift-threshold">
            DRIFT ALERT THRESHOLD (% POINTS)
          </label>
          <input
            id="drift-threshold"
            type="number"
            min={1}
            max={20}
            value={driftThresholdPct}
            onChange={(e) =>
              setDriftThresholdPct(
                Math.min(20, Math.max(1, parseInt(e.target.value, 10) || 3)),
              )
            }
            className="settings-number-input settings-number-input--mono"
          />
          <p className="settings-hint">
            Show a review alert when an override drifts more than this far from
            the row-count fraction. Default: 3%.
          </p>
        </div>

        {driftError && (
          <p className="settings-error" role="alert">{driftError}</p>
        )}

        {driftStatus === 'saved' && (
          <p className="settings-success" role="status">Drift threshold saved.</p>
        )}

        <div className="settings-overrides-actions">
          <button
            type="button"
            className="settings-btn-primary"
            onClick={() => { void handleSaveDriftThreshold() }}
            disabled={driftStatus === 'saving'}
          >
            {driftStatus === 'saving' ? 'SAVING…' : 'SAVE THRESHOLD'}
          </button>

          <button
            type="button"
            className="settings-btn-secondary"
            onClick={() => void navigate('/admin/cubes')}
          >
            REVIEW OVERRIDES
          </button>
        </div>
      </section>
    </div>
  )
}

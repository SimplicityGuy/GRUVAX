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
 * Phase 6 additions (LED-04, LED-05, D-19):
 *   - LEDs section: six per-state color pickers, three brightness sliders,
 *     highlight TTL, retain mode toggle, retain timeout
 *   - ColorBlindPreview next to each color picker (D-18, zero new deps)
 *   - Nordic Grid token swatches as color presets
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { changePin, getAdminSettings, putAdminSettings } from '../../api/adminClient'
import { ColorBlindPreview } from '../../components/ColorBlindPreview'
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

  // Phase 6: LED colors — six per-state colors (LED-05)
  const [ledColorPosition, setLedColorPosition] = useState('#FFD700')
  const [ledColorLabelSpan, setLedColorLabelSpan] = useState('#7C3AED')
  const [ledColorError, setLedColorError] = useState('#E63946')
  const [ledColorSetup, setLedColorSetup] = useState('#0077B6')
  const [ledColorAllOff, setLedColorAllOff] = useState('#000000')
  const [ledColorAmbient, setLedColorAmbient] = useState('#0051A2')
  // Phase 6: LED brightness tiers (LED-04, D-24 naming — three distinct tiers)
  const [ledBrightnessSpan, setLedBrightnessSpan] = useState(128)       // label-span tier
  const [ledBrightnessActive, setLedBrightnessActive] = useState(255)   // position tier
  const [ledBrightnessAmbient, setLedBrightnessAmbient] = useState(40)  // idle baseline
  // Phase 6: LED highlight lifecycle (D-25)
  const [ledHighlightTtl, setLedHighlightTtl] = useState(180)
  const [ledRetainMode, setLedRetainMode] = useState(false)
  const [ledRetainTtl, setLedRetainTtl] = useState(900)
  const [ledsStatus, setLedsStatus] = useState<SaveStatus>('idle')
  const [ledsError, setLedsError] = useState('')

  // Load current settings on mount — use backend key names (WR-01)
  useEffect(() => {
    getAdminSettings()
      .then((s) => {
        setCapacity(s.cube_nominal_capacity)
        setIdleMin(Math.round(s.session_idle_ttl_seconds / 60))
        // Phase 6: LED settings (use nullish fallback to migration 0006 defaults)
        if (s.led_color_position) setLedColorPosition(s.led_color_position)
        if (s.led_color_label_span) setLedColorLabelSpan(s.led_color_label_span)
        if (s.led_color_error) setLedColorError(s.led_color_error)
        if (s.led_color_setup) setLedColorSetup(s.led_color_setup)
        if (s.led_color_all_off) setLedColorAllOff(s.led_color_all_off)
        if (s.led_color_ambient) setLedColorAmbient(s.led_color_ambient)
        if (s.led_brightness_span !== undefined) setLedBrightnessSpan(s.led_brightness_span)
        if (s.led_brightness_active !== undefined) setLedBrightnessActive(s.led_brightness_active)
        if (s.led_brightness_ambient !== undefined) setLedBrightnessAmbient(s.led_brightness_ambient)
        if (s.led_highlight_active_ttl_seconds !== undefined) setLedHighlightTtl(s.led_highlight_active_ttl_seconds)
        if (s.led_highlight_retain_mode !== undefined) setLedRetainMode(s.led_highlight_retain_mode)
        if (s.led_highlight_retain_ttl_seconds !== undefined) setLedRetainTtl(s.led_highlight_retain_ttl_seconds)
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

  // Phase 6: Save LED settings (LED-04, LED-05, D-24, D-25)
  const handleSaveLeds = async () => {
    setLedsStatus('saving')
    setLedsError('')
    try {
      await putAdminSettings({
        led_color_position: ledColorPosition,
        led_color_label_span: ledColorLabelSpan,
        led_color_error: ledColorError,
        led_color_setup: ledColorSetup,
        led_color_all_off: ledColorAllOff,
        led_color_ambient: ledColorAmbient,
        led_brightness_span: ledBrightnessSpan,
        led_brightness_active: ledBrightnessActive,
        led_brightness_ambient: ledBrightnessAmbient,
        led_highlight_active_ttl_seconds: ledHighlightTtl,
        led_highlight_retain_mode: ledRetainMode,
        led_highlight_retain_ttl_seconds: ledRetainTtl,
      })
      setLedsStatus('saved')
      setTimeout(() => setLedsStatus('idle'), 2000)
    } catch {
      setLedsStatus('error')
      setLedsError('Failed to save LED settings. Please try again.')
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

      {/* ── LEDs (Phase 6, LED-04, LED-05, D-18, D-19) ─────────────────────── */}
      <section className="settings-section settings-section--leds" aria-labelledby="leds-heading">
        <h2 id="leds-heading" className="settings-heading">LEDS</h2>

        {/* ── Color pickers ─────────────────────────────────────────────────── */}
        {(
          [
            { id: 'led-color-position',   label: 'POSITION COLOR',   value: ledColorPosition,   setter: setLedColorPosition },
            { id: 'led-color-label-span', label: 'LABEL SPAN COLOR', value: ledColorLabelSpan,  setter: setLedColorLabelSpan },
            { id: 'led-color-error',      label: 'ERROR COLOR',      value: ledColorError,      setter: setLedColorError },
            { id: 'led-color-setup',      label: 'SETUP COLOR',      value: ledColorSetup,      setter: setLedColorSetup },
            { id: 'led-color-all-off',    label: 'ALL OFF COLOR',    value: ledColorAllOff,     setter: setLedColorAllOff },
            { id: 'led-color-ambient',    label: 'AMBIENT COLOR',    value: ledColorAmbient,    setter: setLedColorAmbient },
          ] as const
        ).map(({ id, label, value, setter }) => (
          <div key={id} className="settings-field">
            <label className="settings-label" htmlFor={id}>{label}</label>
            <div className="settings-color-row">
              <input
                id={id}
                type="color"
                value={value}
                onChange={(e) => setter(e.target.value)}
                className="settings-color-input"
              />
              <div className="settings-color-presets" aria-label="Nordic Grid preset colors">
                {['#0051A2', '#FFDA00', '#F7F9FC'].map((preset) => (
                  <button
                    key={preset}
                    type="button"
                    className="settings-color-preset-btn"
                    style={{ backgroundColor: preset }}
                    onClick={() => setter(preset)}
                    aria-label={`Set to ${preset}`}
                    title={preset}
                  />
                ))}
              </div>
              <ColorBlindPreview hex={value} />
            </div>
          </div>
        ))}

        {/* ── Brightness sliders ───────────────────────────────────────────── */}
        {(
          [
            { id: 'led-brightness-span',    label: 'SPAN BRIGHTNESS (LABEL SPAN)',   value: ledBrightnessSpan,    setter: setLedBrightnessSpan },
            { id: 'led-brightness-active',  label: 'ACTIVE BRIGHTNESS (POSITION)',   value: ledBrightnessActive,  setter: setLedBrightnessActive },
            { id: 'led-brightness-ambient', label: 'AMBIENT BRIGHTNESS (IDLE)',       value: ledBrightnessAmbient, setter: setLedBrightnessAmbient },
          ] as const
        ).map(({ id, label, value, setter }) => (
          <div key={id} className="settings-field">
            <label className="settings-label" htmlFor={id}>{label}</label>
            <div className="settings-range-row">
              <input
                id={id}
                type="range"
                min={0}
                max={255}
                value={value}
                onChange={(e) => setter(parseInt(e.target.value, 10))}
                className="settings-range-input"
              />
              <span className="settings-value-mono">{value}</span>
            </div>
          </div>
        ))}

        {/* ── Highlight lifecycle ─────────────────────────────────────────── */}
        <div className="settings-field">
          <label className="settings-label" htmlFor="led-highlight-ttl">
            HIGHLIGHT TTL (SECONDS)
          </label>
          <input
            id="led-highlight-ttl"
            type="number"
            min={10}
            max={3600}
            value={ledHighlightTtl}
            onChange={(e) =>
              setLedHighlightTtl(Math.min(3600, Math.max(10, parseInt(e.target.value, 10) || 180)))
            }
            className="settings-number-input settings-number-input--mono"
          />
          <p className="settings-hint">
            How long a positioned-record highlight stays lit before auto-reverting. Default: 180 s.
          </p>
        </div>

        <div className="settings-field">
          <label className="settings-label settings-label--toggle" htmlFor="led-retain-mode">
            RETAIN MODE
            <span className="settings-hint">
              Keep the last highlight visible when idle instead of fading out.
            </span>
          </label>
          <input
            id="led-retain-mode"
            type="checkbox"
            checked={ledRetainMode}
            onChange={(e) => setLedRetainMode(e.target.checked)}
            className="settings-toggle"
          />
        </div>

        {ledRetainMode && (
          <div className="settings-field">
            <label className="settings-label" htmlFor="led-retain-ttl">
              RETAIN TIMEOUT (SECONDS)
            </label>
            <input
              id="led-retain-ttl"
              type="number"
              min={60}
              max={86400}
              value={ledRetainTtl}
              onChange={(e) =>
                setLedRetainTtl(Math.min(86400, Math.max(60, parseInt(e.target.value, 10) || 900)))
              }
              className="settings-number-input settings-number-input--mono"
            />
            <p className="settings-hint">
              How long the retained highlight stays before fading. Default: 900 s.
            </p>
          </div>
        )}

        {ledsError && (
          <p className="settings-error" role="alert">{ledsError}</p>
        )}

        {ledsStatus === 'saved' && (
          <p className="settings-success" role="status">LED settings saved.</p>
        )}

        <div className="settings-actions settings-actions--leds">
          <button
            type="button"
            className="settings-btn-primary"
            onClick={() => { void handleSaveLeds() }}
            disabled={ledsStatus === 'saving'}
          >
            {ledsStatus === 'saving' ? 'SAVING…' : 'SAVE LED SETTINGS'}
          </button>
          {/* Plan 06-04 will add All-off + Run Diagnostic buttons here */}
        </div>
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

        <div className="settings-actions">
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
            className="settings-review-overrides-btn"
            onClick={() => void navigate('/admin/cubes')}
          >
            REVIEW OVERRIDES
          </button>
        </div>
      </section>
    </div>
  )
}

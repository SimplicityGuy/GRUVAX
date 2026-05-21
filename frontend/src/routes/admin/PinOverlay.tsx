/**
 * PinOverlay — full-viewport PIN entry modal (UI-SPEC §A).
 *
 * Mounts over the admin shell whenever ``isLoggedIn === false``.
 * Manages the PIN entry state machine:
 *
 *   idle → entering (digit tap) → submitting (4th digit) →
 *     success (login OK, call setAdminLoggedIn, dismiss)
 *     wrong  (shake + flash dots red 400ms, reset)
 *     ratelimit (hide dots, show retry countdown)
 *
 * Security: PIN digits are never stored in a text input — they are tracked
 * in component state as an array and sent as a plain string to adminLogin().
 * The overlay uses ``role="dialog" aria-modal="true"`` for screen readers.
 */

import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { adminLogin, AuthError, RateLimitError } from '../../api/adminClient'
import { useAdminStore } from '../../state/adminStore'
import { NumericKeypad } from './NumericKeypad'
import './admin.css'

const PIN_LENGTH = 4

type PinStatus = 'idle' | 'submitting' | 'error' | 'ratelimit'

interface PinOverlayProps {
  /** When true, the overlay is shown even though there is an existing session
   *  (Lock button tapped — re-auth without ending the session). */
  isLocked?: boolean
}

export function PinOverlay({ isLocked = false }: PinOverlayProps) {
  const headingId = useId()
  const { setAdminLoggedIn } = useAdminStore()

  const [digits, setDigits] = useState<string[]>([])
  const [status, setStatus] = useState<PinStatus>('idle')
  const [errorMsg, setErrorMsg] = useState('')
  const [retrySeconds, setRetrySeconds] = useState(0)
  const [shake, setShake] = useState(false)

  const retryTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const submitPin = useCallback(async (pin: string) => {
    setStatus('submitting')
    try {
      const { csrf_token: csrfToken } = await adminLogin(pin)
      // On success, fetch session times then call setAdminLoggedIn.
      // adminGetSession() requires the session cookie which is now set.
      // For simplicity, derive expires_at from the idle TTL default (10 min).
      // AdminShell will poll /api/admin/session immediately and update.
      const now = new Date()
      const expires = new Date(now.getTime() + 10 * 60 * 1000).toISOString()
      const hardCap = new Date(now.getTime() + 30 * 60 * 1000).toISOString()
      setAdminLoggedIn(expires, hardCap, csrfToken)
    } catch (err) {
      if (err instanceof RateLimitError) {
        setStatus('ratelimit')
        setRetrySeconds(err.retryAfterSeconds)
        setDigits([])
        setErrorMsg(`Too many attempts. Try again in ${err.retryAfterSeconds}s.`)
      } else if (err instanceof AuthError) {
        // Wrong PIN — shake + flash
        setStatus('error')
        setShake(true)
        setTimeout(() => {
          setShake(false)
          setStatus('idle')
          setDigits([])
        }, 400)
      } else {
        setStatus('error')
        setErrorMsg('Login failed. Please try again.')
        setTimeout(() => {
          setStatus('idle')
          setDigits([])
          setErrorMsg('')
        }, 2000)
      }
    }
  }, [setAdminLoggedIn])

  // Auto-submit on 4th digit
  useEffect(() => {
    if (digits.length === PIN_LENGTH && status === 'idle') {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- async PIN submission; setState happens inside the adminLogin promise, not synchronously
      void submitPin(digits.join(''))
    }
  }, [digits, status, submitPin])

  // Countdown for rate-limit retry
  useEffect(() => {
    if (status === 'ratelimit' && retrySeconds > 0) {
      retryTimerRef.current = setInterval(() => {
        setRetrySeconds((s) => {
          if (s <= 1) {
            clearInterval(retryTimerRef.current!)
            setStatus('idle')
            setDigits([])
            setErrorMsg('')
            return 0
          }
          return s - 1
        })
      }, 1000)
    }
    return () => {
      if (retryTimerRef.current) clearInterval(retryTimerRef.current)
    }
  }, [status, retrySeconds])

  const handleDigit = useCallback((d: string) => {
    if (status === 'submitting' || status === 'ratelimit') return
    setDigits((prev) => (prev.length < PIN_LENGTH ? [...prev, d] : prev))
  }, [status])

  const handleBackspace = useCallback(() => {
    if (status === 'submitting' || status === 'ratelimit') return
    setDigits((prev) => prev.slice(0, -1))
    if (status === 'error') {
      setStatus('idle')
      setErrorMsg('')
    }
  }, [status])

  const isError = status === 'error'
  const isRateLimit = status === 'ratelimit'
  const isSubmitting = status === 'submitting'

  return (
    <div className="pin-overlay" role="dialog" aria-modal="true" aria-labelledby={headingId}>
      <div className={`pin-card${shake ? ' pin-card--shake' : ''}`}>
        {/* Logo mark */}
        <div className="pin-logo" aria-hidden="true">
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <rect x="2" y="2" width="44" height="44" rx="8" stroke="var(--gruvax-blue)" strokeWidth="3" fill="var(--gruvax-white)" />
            <rect x="8" y="20" width="14" height="8" rx="2" fill="var(--gruvax-yellow)" />
            <rect x="26" y="20" width="14" height="8" rx="2" fill="var(--gruvax-blue)" />
          </svg>
        </div>

        <h1 id={headingId} className="pin-heading">
          {isLocked ? 'LOCKED' : 'ENTER PIN'}
        </h1>

        {!isRateLimit && (
          <div className="pin-dots" aria-label={`${digits.length} of ${PIN_LENGTH} digits entered`} aria-live="polite">
            {Array.from({ length: PIN_LENGTH }, (_, i) => (
              <span
                key={i}
                className={`pin-dot${i < digits.length ? ' pin-dot--filled' : ''}${isError ? ' pin-dot--error' : ''}`}
                aria-hidden="true"
              />
            ))}
          </div>
        )}

        {isRateLimit && (
          <p className="pin-error pin-ratelimit" role="alert">
            {`Too many attempts. Try again in ${retrySeconds}s.`}
          </p>
        )}

        {errorMsg && !isRateLimit && (
          <p className="pin-error" role="alert">
            {isError ? 'Incorrect PIN. Try again.' : errorMsg}
          </p>
        )}

        {!isRateLimit && (
          <NumericKeypad
            onDigit={handleDigit}
            onBackspace={handleBackspace}
            disabled={isSubmitting || isError}
          />
        )}
      </div>
    </div>
  )
}

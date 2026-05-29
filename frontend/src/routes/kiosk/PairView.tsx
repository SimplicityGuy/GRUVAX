/**
 * PairView — /pair route (DEV-03 kiosk pairing UX).
 *
 * Wall-mounted kiosk screen that:
 *   1. Fetches a 4-digit pairing code via POST /api/devices/pairing-codes
 *   2. Displays the code in 96px DM Mono with a M:SS countdown
 *   3. Auto-rerolls the code when the countdown reaches 0:00
 *   4. Polls GET /api/devices/me every 3s; on state=paired runs the success
 *      transition and navigates to '/' (bound-profile search)
 *   5. D3-03: if the session already reports is_device_paired, redirects to '/'
 *      immediately (never renders the code)
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 * Typography per 03-UI-SPEC.md Surface 1.
 * Motion per 03-UI-SPEC.md Motion Contract.
 *
 * Implementation note: the pairing-code fetch and countdown use direct
 * fetch+setState rather than TanStack Query, to ensure the countdown is
 * immediately available in the DOM after the fetch resolves (no TanStack
 * Query scheduler delay needed for tests or initial render).
 * The /api/devices/me poll uses TanStack Query refetchInterval as designed.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { CheckCircle2, Loader2 } from 'lucide-react'
import { getSession } from '../../api/session'
import { getDeviceMe } from '../../api/devices'
import './pair.css'

/** Format milliseconds remaining as M:SS. */
function formatCountdown(ms: number): string {
  if (ms <= 0) return '0:00'
  const totalSeconds = Math.floor(ms / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

interface PairingCodeData {
  code: string
  expires_at: string
}

type PairStatus = 'loading' | 'active' | 'expiring' | 'expired' | 'paired'

export function PairView() {
  const navigate = useNavigate()

  // Pairing code state — managed directly (not via TanStack Query)
  // so the countdown renders immediately after fetch resolves.
  const [pairingCode, setPairingCode] = useState<PairingCodeData | null>(null)
  const [isCodeFetching, setIsCodeFetching] = useState(false)
  const fetchAbortRef = useRef<AbortController | null>(null)

  // Countdown state
  const [remainingMs, setRemainingMs] = useState<number | null>(null)
  const [pairStatus, setPairStatus] = useState<PairStatus>('loading')
  const countdownIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  // Guard: track whether reroll has been triggered to avoid double-firing
  const rerollTriggeredRef = useRef(false)

  // Milestone announcer ref (a11y — aria-live="assertive" hidden node)
  const announcerRef = useRef<HTMLSpanElement>(null)
  const lastMilestoneRef = useRef<number | null>(null)

  // ── D3-03: already-paired session guard ─────────────────────────────────
  useEffect(() => {
    getSession()
      .then((data) => {
        if (data.is_device_paired && data.bound_profile_id) {
          void navigate('/', { replace: true })
        }
      })
      .catch(() => {
        // Degrade gracefully — session unavailable, stay on /pair
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Pairing code fetcher ─────────────────────────────────────────────────
  const fetchNewCode = useCallback(async () => {
    if (isCodeFetching) return
    // Cancel any in-flight fetch
    fetchAbortRef.current?.abort()
    const controller = new AbortController()
    fetchAbortRef.current = controller

    setIsCodeFetching(true)
    try {
      const res = await fetch('/api/devices/pairing-codes', {
        method: 'POST',
        signal: controller.signal,
      })
      if (!res.ok) throw new Error(`Failed: ${res.status}`)
      const data = await res.json() as PairingCodeData
      setPairingCode(data)
    } catch {
      // Fetch failed or aborted — degrade gracefully (keep old code displayed)
    } finally {
      setIsCodeFetching(false)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Initial fetch on mount
  useEffect(() => {
    void fetchNewCode()
    return () => {
      fetchAbortRef.current?.abort()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Countdown effect — fires when a new pairingCode is received ──────────
  useEffect(() => {
    if (!pairingCode?.expires_at) return

    // Clear any running interval
    if (countdownIntervalRef.current) {
      clearInterval(countdownIntervalRef.current)
    }
    rerollTriggeredRef.current = false
    lastMilestoneRef.current = null

    const computeRemaining = () => {
      const expiresMs = new Date(pairingCode.expires_at).getTime()
      return expiresMs - Date.now()
    }

    const initial = computeRemaining()
    const clampedInitial = Math.max(0, initial)
    setRemainingMs(clampedInitial)
    setPairStatus(clampedInitial <= 60_000 ? 'expiring' : 'active')

    countdownIntervalRef.current = setInterval(() => {
      const rem = computeRemaining()
      const clamped = Math.max(0, rem)
      setRemainingMs(clamped)

      // Milestone announcements (a11y — announce at 60s, 30s, 10s)
      const totalSec = Math.floor(clamped / 1000)
      const milestones = [60, 30, 10]
      for (const m of milestones) {
        if (totalSec === m && lastMilestoneRef.current !== m) {
          lastMilestoneRef.current = m
          if (announcerRef.current) {
            announcerRef.current.textContent = `${m} seconds remaining`
          }
        }
      }

      if (clamped <= 60_000 && pairStatus !== 'expired' && pairStatus !== 'paired') {
        setPairStatus('expiring')
      }

      if (clamped <= 0 && !rerollTriggeredRef.current) {
        rerollTriggeredRef.current = true
        setPairStatus('expired')
        // Auto-reroll: fetch a new code
        void fetchNewCode()
      }
    }, 1000)

    return () => {
      if (countdownIntervalRef.current) {
        clearInterval(countdownIntervalRef.current)
      }
    }
    // pairStatus is intentionally omitted — we only restart on new code
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pairingCode?.expires_at, fetchNewCode])

  // ── Device-state poll ────────────────────────────────────────────────────
  const { data: deviceState } = useQuery({
    queryKey: ['devices', 'me'],
    queryFn: getDeviceMe,
    refetchInterval: (query) => {
      return query.state.data?.state === 'paired' ? false : 3000
    },
    refetchOnWindowFocus: false,
  })

  // ── Paired state handler ─────────────────────────────────────────────────
  const pairedHandledRef = useRef(false)
  const handlePaired = useCallback(() => {
    if (pairedHandledRef.current) return
    pairedHandledRef.current = true
    setPairStatus('paired')
    // Stop countdown
    if (countdownIntervalRef.current) {
      clearInterval(countdownIntervalRef.current)
    }
    // Success transition: hold 800ms then navigate
    setTimeout(() => {
      void navigate('/', { replace: true })
    }, 800)
  }, [navigate])

  useEffect(() => {
    if (deviceState?.state === 'paired') {
      handlePaired()
    }
  }, [deviceState, handlePaired])

  // ── Derived status ───────────────────────────────────────────────────────
  const isPaired = pairStatus === 'paired'
  const isExpired = pairStatus === 'expired'
  const isLoading = isCodeFetching && !pairingCode
  const isWarning = pairStatus === 'expiring'

  const digits = isLoading || !pairingCode
    ? ['—', '—', '—', '—']
    : isExpired
      ? ['—', '—', '—', '—']
      : (pairingCode.code.split('') ?? ['—', '—', '—', '—'])

  const countdownText =
    remainingMs === null
      ? ''
      : isWarning && !isPaired
        ? `${formatCountdown(remainingMs)} remaining — hurry!`
        : `${formatCountdown(remainingMs)} remaining`

  return (
    <div className="pair-page">
      {/* Hidden milestone announcer (a11y — assertive, announce at milestones only) */}
      <span
        ref={announcerRef}
        aria-live="assertive"
        aria-atomic="true"
        className="pair-milestone-announcer"
      />

      {/* GRUVAX icon mark */}
      <div className="pair-icon-mark" aria-hidden="true">
        <svg
          width="48"
          height="48"
          viewBox="0 0 48 48"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
        >
          <rect
            x="2"
            y="2"
            width="44"
            height="44"
            rx="8"
            stroke="var(--gruvax-blue)"
            strokeWidth="3"
            fill="var(--gruvax-white)"
          />
          <rect x="8" y="20" width="14" height="8" rx="2" fill="var(--gruvax-yellow)" />
          <rect x="26" y="20" width="14" height="8" rx="2" fill="var(--gruvax-blue)" />
        </svg>
      </div>

      {/* Screen heading */}
      <h1 className="pair-heading">PAIR THIS SCREEN</h1>

      {/* Instruction */}
      <p className="pair-instruction">Enter this code in the admin app</p>

      {/* Code card */}
      <div
        className={`pair-code-card${isPaired ? ' pair-code-card--success' : ''}${isExpired ? ' pair-code-card--expired' : ''}`}
        role="status"
        aria-live="polite"
        aria-label={
          isPaired
            ? 'Paired — navigating'
            : isLoading
              ? 'Loading pairing code'
              : isExpired
                ? 'Generating new code'
                : `Pairing code: ${pairingCode?.code ?? ''}`
        }
      >
        {isPaired ? (
          <div className="pair-code-success">
            <CheckCircle2 size={48} aria-hidden="true" />
            <span className="pair-code-success-text">PAIRED — navigating…</span>
          </div>
        ) : isExpired ? (
          <span className="pair-code-expired-text">Generating new code…</span>
        ) : (
          <div className="pair-code-digits">
            {digits.map((d, i) => (
              <span key={i} className="pair-code-digit">
                {d}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Waiting status + countdown */}
      {!isPaired && (
        <div className="pair-status-row">
          {!isExpired && (
            <div className="pair-waiting-pill" aria-live="off">
              <Loader2 size={16} className="pair-spinner" aria-hidden="true" />
              <span className="pair-waiting-label">WAITING FOR PAIRING…</span>
            </div>
          )}
          {remainingMs !== null && !isExpired && (
            <p
              className={`pair-countdown${isWarning ? ' pair-countdown--warning' : ''}`}
              aria-live="off"
            >
              {countdownText}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

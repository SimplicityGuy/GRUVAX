/**
 * AdminShell — authenticated admin chrome (UI-SPEC §B).
 *
 * Renders the blue top bar with:
 *   - GRUVAX ADMIN wordmark
 *   - Session countdown pill (mm:ss, aria-live="polite", last-60s → warning color)
 *   - Lock button (re-shows PinOverlay without ending session — D-03c)
 *   - Logout button (immediate, no confirm — ADMN-08)
 *
 * Shows <PinOverlay> when isLoggedIn === false (including Lock state).
 * Polls GET /api/admin/session every 30s to keep countdown in sync with
 * the server's sliding window; on 401, transitions back to PinOverlay.
 * Renders <Outlet/> for child admin routes (/admin/settings, etc.).
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Outlet, NavLink } from 'react-router'
import { adminGetSession, adminLogout, AuthError } from '../../api/adminClient'
import { useAdminStore } from '../../state/adminStore'
import { PinOverlay } from './PinOverlay'
import './admin.css'

const POLL_INTERVAL_MS = 30_000 // 30 s
const WARNING_THRESHOLD_MS = 60_000 // last 60 s → warning color

function formatCountdown(ms: number): string {
  if (ms <= 0) return '0:00'
  const totalSeconds = Math.floor(ms / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

export function AdminShell() {
  const { isLoggedIn, sessionExpiresAt, hardCapExpiresAt, setAdminLoggedOut, refreshExpiry } =
    useAdminStore()

  const [isLocked, setIsLocked] = useState(false)
  const [nowMs, setNowMs] = useState(() => Date.now())
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Refs to avoid stale closures inside the long-lived tick interval
  const isLoggedInRef = useRef(isLoggedIn)
  const sessionExpiresAtRef = useRef(sessionExpiresAt)
  isLoggedInRef.current = isLoggedIn
  sessionExpiresAtRef.current = sessionExpiresAt

  // ── Tick every second for countdown + expiry check ───────────────────────
  // The expiry check is collapsed into this interval so the setState calls
  // live inside a timer callback (not a synchronous in-effect setState).
  useEffect(() => {
    tickRef.current = setInterval(() => {
      const t = Date.now()
      setNowMs(t)
      if (isLoggedInRef.current && sessionExpiresAtRef.current > 0 && t >= sessionExpiresAtRef.current) {
        setAdminLoggedOut()
        setIsLocked(false)
      }
    }, 1000)
    return () => {
      if (tickRef.current) clearInterval(tickRef.current)
    }
  }, [setAdminLoggedOut])

  // ── Poll /api/admin/session to keep sliding window in sync ───────────────
  const pollSession = useCallback(async () => {
    if (!isLoggedIn) return
    try {
      const session = await adminGetSession()
      refreshExpiry(session.expires_at)
    } catch (err) {
      if (err instanceof AuthError) {
        // Session expired or revoked — force re-auth
        setAdminLoggedOut()
        setIsLocked(false)
      }
    }
  }, [isLoggedIn, refreshExpiry, setAdminLoggedOut])

  useEffect(() => {
    if (!isLoggedIn) return
    // Defer the immediate poll into a 0ms timer callback so setState inside
    // pollSession is not called synchronously in the effect body.
    const immediateId = setTimeout(() => { void pollSession() }, 0)
    pollRef.current = setInterval(() => { void pollSession() }, POLL_INTERVAL_MS)
    return () => {
      clearTimeout(immediateId)
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [isLoggedIn, pollSession])

  const handleLogout = useCallback(async () => {
    await adminLogout().catch(() => {/* ignore network errors on logout */})
    setAdminLoggedOut()
    setIsLocked(false)
  }, [setAdminLoggedOut])

  const handleLock = useCallback(() => {
    setIsLocked(true)
  }, [])

  const idleRemainingMs = sessionExpiresAt > 0 ? sessionExpiresAt - nowMs : 0
  const isExpiringSoon = idleRemainingMs > 0 && idleRemainingMs < WARNING_THRESHOLD_MS

  const hardCapRemainingMs = hardCapExpiresAt > 0 ? hardCapExpiresAt - nowMs : 0
  const showHardCapWarning = hardCapRemainingMs > 0 && hardCapRemainingMs < 5 * 60_000

  const showOverlay = !isLoggedIn || isLocked

  return (
    <div className="admin-shell">
      {/* Top bar (UI-SPEC §B) */}
      <header className="admin-topbar" role="banner">
        <div className="admin-topbar-brand">
          <span className="admin-topbar-wordmark">GRUVAX ADMIN</span>
        </div>

        <nav className="admin-topbar-nav" aria-label="Admin navigation">
          <NavLink
            to="/admin/settings"
            className={({ isActive }) =>
              `admin-nav-tab${isActive ? ' admin-nav-tab--active' : ''}`
            }
          >
            SETTINGS
          </NavLink>
          <NavLink
            to="/admin/cubes"
            className={({ isActive }) =>
              `admin-nav-tab${isActive ? ' admin-nav-tab--active' : ''}`
            }
          >
            CUBES
          </NavLink>
          <NavLink
            to="/admin/history"
            className={({ isActive }) =>
              `admin-nav-tab${isActive ? ' admin-nav-tab--active' : ''}`
            }
          >
            HISTORY
          </NavLink>
        </nav>

        <div className="admin-topbar-actions">
          {/* Session countdown pill */}
          {isLoggedIn && sessionExpiresAt > 0 && (
            <span
              className={`admin-countdown${isExpiringSoon ? ' admin-countdown--warning' : ''}`}
              aria-live="polite"
              aria-label={`Session expires in ${formatCountdown(idleRemainingMs)}`}
              role="timer"
            >
              {formatCountdown(idleRemainingMs)}
            </span>
          )}

          {/* Lock button */}
          {isLoggedIn && (
            <button
              type="button"
              className="admin-icon-btn"
              onClick={handleLock}
              aria-label="Lock screen"
            >
              {/* Lucide Lock icon */}
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
                focusable="false"
              >
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
            </button>
          )}

          {/* Logout button */}
          <button
            type="button"
            className="admin-icon-btn"
            onClick={() => { void handleLogout() }}
            aria-label="Log out"
          >
            {/* Lucide LogOut icon */}
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
              focusable="false"
            >
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
          </button>
        </div>
      </header>

      {/* Hard-cap warning banner */}
      {isLoggedIn && showHardCapWarning && (
        <div className="admin-hardcap-banner" role="alert">
          Session ends soon — activity cannot extend it.
        </div>
      )}

      {/* Main content area */}
      <main className="admin-content">
        {isLoggedIn ? <Outlet /> : null}
      </main>

      {/* PIN overlay — shown when not logged in OR when screen is locked */}
      {showOverlay && (
        <PinOverlay isLocked={isLocked} />
      )}
    </div>
  )
}

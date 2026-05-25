/**
 * ReshuffleBanner — resume/discard banner for in-progress reshuffle drafts (D-06, D-07, SC3).
 *
 * Placed directly inside AdminShell's <main> content area, above <Outlet/>.
 * Returns null when reshuffleDraft === null — no-op when no draft is in progress.
 *
 * Design constraints (CLAUDE.md + 07-UI-SPEC.md Surface 3):
 * - All colors via --gruvax-* tokens; NO hardcoded hex.
 * - All user-supplied strings via JSX {} interpolation; never innerHTML.
 * - Discard confirm is inline (no modal) — two-step banner content swap (D-07).
 * - No time-based auto-expiry (D-07) — banner shows regardless of draft age.
 * - CONTINUE navigates to /admin/wizard?mode=reshuffle for re-validate (D-06).
 */

import { useState } from 'react'
import { useNavigate } from 'react-router'
import { useAdminStore } from '../../state/adminStore'
import './admin.css'

// ── Relative time helper ──────────────────────────────────────────────────────

function formatRelativeTime(isoString: string): string {
  try {
    const diffMs = Date.now() - new Date(isoString).getTime()
    const diffMinutes = Math.floor(diffMs / 60_000)
    if (diffMinutes < 1) return 'just now'
    if (diffMinutes < 60) return `${diffMinutes} minute${diffMinutes !== 1 ? 's' : ''} ago`
    const diffHours = Math.floor(diffMinutes / 60)
    if (diffHours < 24) return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`
    const diffDays = Math.floor(diffHours / 24)
    return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`
  } catch {
    return 'some time ago'
  }
}

// ── Component ─────────────────────────────────────────────────────────────────

export function ReshuffleBanner() {
  const navigate = useNavigate()
  const { reshuffleDraft, setReshuffleDraft } = useAdminStore()
  const [confirming, setConfirming] = useState(false)

  // Returns null when no draft in progress (D-06)
  if (!reshuffleDraft) return null

  const startedAgo = formatRelativeTime(reshuffleDraft.startedAt)
  // Use a reasonable estimate for total steps (will be refined when cubes load)
  const completedSteps = reshuffleDraft.completedSteps
  const totalSteps = Object.keys(reshuffleDraft.cuts).length || completedSteps || '?'

  function handleContinue() {
    void navigate('/admin/wizard?mode=reshuffle')
  }

  function handleDiscardConfirm() {
    setReshuffleDraft(null)  // clears store + localStorage (D-07)
    setConfirming(false)
  }

  return (
    <div className="reshuffle-banner" role="region" aria-label="Reshuffle in progress">
      {confirming ? (
        /* Inline discard confirm — no modal (D-07, UI-SPEC Surface 3) */
        <div className="reshuffle-banner-confirm">
          <p className="reshuffle-banner-confirm-text">
            Are you sure? This will delete your in-progress reshuffle draft.
          </p>
          <div className="reshuffle-banner-actions">
            <button
              type="button"
              className="reshuffle-btn reshuffle-btn--destructive"
              onClick={handleDiscardConfirm}
            >
              YES, DISCARD
            </button>
            <button
              type="button"
              className="reshuffle-btn reshuffle-btn--outline"
              onClick={() => setConfirming(false)}
            >
              KEEP DRAFT
            </button>
          </div>
        </div>
      ) : (
        /* Normal banner state */
        <>
          <p className="reshuffle-banner-heading">
            {`RESHUFFLE IN PROGRESS — ${completedSteps} OF ${totalSteps} STEPS DONE`}
          </p>
          <p className="reshuffle-banner-subline">
            {`Started ${startedAgo}`}
          </p>
          <div className="reshuffle-banner-actions">
            <button
              type="button"
              className="reshuffle-btn reshuffle-btn--primary"
              onClick={handleContinue}
            >
              CONTINUE
            </button>
            <button
              type="button"
              className="reshuffle-btn reshuffle-btn--discard"
              onClick={() => setConfirming(true)}
            >
              DISCARD
            </button>
          </div>
        </>
      )}
    </div>
  )
}

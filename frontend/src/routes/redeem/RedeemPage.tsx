/**
 * RedeemPage — public member invite-code redemption page (/redeem/:code).
 *
 * No PIN gate — fully public route (D-03). Accessible to any LAN visitor.
 *
 * States:
 *   loading   — GET /api/invite-codes/:code in flight (centered spinner)
 *   active    — form shown with profile display_name, PAT input + Eye/EyeOff toggle
 *   invalid   — error card with no form (expired / used / invalid code)
 *   submitting — form disabled, CTA shows "CONNECTING…" + Loader2 spinner
 *   success   — terminal state: CheckCircle2 icon + "CONNECTED" heading
 *
 * T-07-13: PAT lives only in component state and the POST body.
 *   Never written to localStorage/sessionStorage/URL.
 *   Input is type="password" with autocomplete="off".
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 */

import { useEffect, useState } from 'react'
import { useParams } from 'react-router'
import { CheckCircle2, Eye, EyeOff, Loader2 } from 'lucide-react'
import { getInviteCode, redeemInviteCode, RedeemApiError } from '../../api/inviteClient'
import type { InviteCodeInfo } from '../../api/types'
import './RedeemPage.css'

type PageState = 'loading' | 'invalid' | 'active' | 'submitting' | 'success'

/** Map backend error types to UI-SPEC §Copywriting Contract copy strings. */
function mapRedeemError(err: unknown): { message: string; inline: boolean } {
  if (err instanceof RedeemApiError) {
    switch (err.errorType) {
      case 'invite_not_found':
        // The backend returns uniform 404 for expired/used/invalid (T-07-10)
        // — we can't distinguish expired vs used on the frontend so show the generic copy.
        return {
          message: 'This invite link is not valid. Check the link and try again.',
          inline: false,
        }
      case 'pat_rejected':
        return {
          message: "This token was not accepted. Check that it's valid and has collection access, then try again.",
          inline: true,
        }
      case 'user_id_collision':
        return {
          message: 'This token belongs to someone who already has a profile. Each person needs their own token.',
          inline: true,
        }
      case 'rate_limited':
        return {
          message: 'Too many attempts. Wait a moment and try again.',
          inline: true,
        }
      case 'upstream_unavailable':
      default:
        return {
          message: 'Could not reach Discogs right now. Try again in a moment.',
          inline: true,
        }
    }
  }
  return {
    message: 'Could not reach Discogs right now. Try again in a moment.',
    inline: true,
  }
}

export function RedeemPage() {
  const { code } = useParams<{ code: string }>()

  const [pageState, setPageState] = useState<PageState>('loading')
  const [inviteInfo, setInviteInfo] = useState<InviteCodeInfo | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [patValue, setPatValue] = useState('')
  const [showPat, setShowPat] = useState(false)
  const [inlineError, setInlineError] = useState<string | null>(null)

  // On mount: validate the code via GET /api/invite-codes/:code.
  // The synchronous setState in the early-return branch is intentional: `code` is a
  // URL param (external system), not React state, so the effect must set state to react
  // to it. Pattern mirrors KioskView SSE handlers.
  useEffect(() => {
    if (!code) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setPageState('invalid')
      setErrorMessage('This invite link is not valid. Check the link and try again.')
      return
    }

    getInviteCode(code)
      .then((info) => {
        setInviteInfo(info)
        setPageState('active')
      })
      .catch(() => {
        setPageState('invalid')
        setErrorMessage('This invite link is not valid. Check the link and try again.')
      })
  }, [code])

  async function handleSubmit() {
    if (!code || !patValue.trim()) return

    setInlineError(null)
    setPageState('submitting')

    try {
      await redeemInviteCode(code, patValue.trim())
      setPageState('success')
    } catch (err) {
      const { message, inline } = mapRedeemError(err)
      if (inline) {
        setPageState('active')
        setInlineError(message)
      } else {
        setPageState('invalid')
        setErrorMessage(message)
      }
    }
  }

  // ── Loading state ──────────────────────────────────────────────────────────
  if (pageState === 'loading') {
    return (
      <div className="redeem-page" role="main">
        <div className="redeem-card">
          <div className="redeem-loading" aria-label="Loading…">
            <Loader2 size={32} className="redeem-loading__spinner" aria-hidden="true" />
          </div>
        </div>
      </div>
    )
  }

  // ── Invalid / error state ─────────────────────────────────────────────────
  if (pageState === 'invalid') {
    return (
      <div className="redeem-page" role="main">
        <div className="redeem-card">
          <img
            src="/gruvax-logo-icon.svg"
            alt="GRUVAX"
            className="redeem-logo"
            width="48"
            height="48"
          />
          <div className="redeem-error-card" role="alert">
            <p className="redeem-error-card__message">{errorMessage}</p>
          </div>
        </div>
      </div>
    )
  }

  // ── Success (terminal) state ───────────────────────────────────────────────
  if (pageState === 'success') {
    return (
      <div className="redeem-page" role="main">
        <div className="redeem-card redeem-card--success">
          <CheckCircle2 size={32} className="redeem-success__icon" aria-hidden="true" />
          <h1 className="redeem-success__heading">CONNECTED</h1>
          <p className="redeem-success__body" role="status">
            Your collection is importing. You can close this page.
          </p>
        </div>
      </div>
    )
  }

  // ── Active / submitting state ──────────────────────────────────────────────
  const displayName = inviteInfo?.display_name ?? ''
  const isSubmitting = pageState === 'submitting'

  return (
    <div className="redeem-page" role="main">
      <div className="redeem-card redeem-card--form">
        {/* GRUVAX icon mark */}
        <img
          src="/gruvax-logo-icon.svg"
          alt="GRUVAX"
          className="redeem-logo"
          width="48"
          height="48"
        />

        {/* Heading */}
        <h1 className="redeem-heading">
          CONNECT {displayName.toUpperCase()}
        </h1>

        {/* Instruction */}
        <p className="redeem-instruction">
          To connect {displayName}'s collection, find your Discogs personal
          access token at discogs.com/settings/developers, then paste it below.
        </p>

        {/* Discogs link */}
        <a
          href="https://www.discogs.com/settings/developers"
          className="redeem-discogs-link"
          target="_blank"
          rel="noopener noreferrer"
        >
          Open Discogs developer settings
        </a>

        {/* PAT field */}
        <label htmlFor="redeem-pat-input" className="redeem-field-label">
          PERSONAL ACCESS TOKEN
        </label>
        <div className="redeem-pat-row">
          <input
            id="redeem-pat-input"
            type={showPat ? 'text' : 'password'}
            className="redeem-pat-input"
            value={patValue}
            onChange={(e) => setPatValue(e.target.value)}
            placeholder="Paste your token here"
            disabled={isSubmitting}
            autoComplete="off"
          />
          <button
            type="button"
            className="redeem-pat-toggle"
            onClick={() => setShowPat((v) => !v)}
            aria-label={showPat ? 'Hide token' : 'Show token'}
            disabled={isSubmitting}
          >
            {showPat
              ? <EyeOff size={16} aria-hidden="true" />
              : <Eye size={16} aria-hidden="true" />
            }
          </button>
        </div>

        {/* Inline error zone */}
        {inlineError && (
          <p className="redeem-inline-error" role="alert">
            {inlineError}
          </p>
        )}

        {/* CTA button */}
        <button
          type="button"
          className="redeem-cta"
          onClick={() => void handleSubmit()}
          disabled={isSubmitting || !patValue.trim()}
          aria-busy={isSubmitting}
        >
          {isSubmitting
            ? (
              <>
                <Loader2 size={16} className="redeem-cta__spinner" aria-hidden="true" />
                CONNECTING…
              </>
            )
            : 'CONNECT COLLECTION'
          }
        </button>
      </div>
    </div>
  )
}

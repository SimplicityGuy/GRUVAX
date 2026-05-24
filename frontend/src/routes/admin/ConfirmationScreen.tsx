/**
 * ConfirmationScreen — post-commit confirmation surface (UI-SPEC Surface 4, D-15, SC5).
 *
 * Displays after a successful wizard/import commit:
 * - Success checkmark
 * - Heading by operation source (SOURCE_HEADINGS map)
 * - Operation sub-line with cube count
 * - change_set_id in DM Mono with a copy button (aria-label="Copy change set ID")
 * - REVERT THIS CHANGE SET → navigates to /admin/history?highlight=<id> (D-15)
 * - BACK TO CUBES → navigates to /admin/cubes
 *
 * Design constraints (CLAUDE.md + 07-UI-SPEC.md):
 * - All colors via --gruvax-* tokens; NO hardcoded hex.
 * - All user-supplied strings via JSX {} interpolation; never innerHTML.
 * - Accessible: copy button has aria-label; icon-only controls labeled.
 */

import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import './admin.css'

// ── Source label maps ────────────────────────────────────────────────────────

const SOURCE_HEADINGS: Record<string, string> = {
  wizard:    'BOUNDARIES COMMITTED',
  reshuffle: 'RESHUFFLE COMMITTED',
  csv:       'IMPORT COMMITTED',
  yaml:      'IMPORT COMMITTED',
}

const SOURCE_SUBLINES: Record<string, string> = {
  wizard:    'Operation: Wizard setup',
  reshuffle: 'Operation: Reshuffle',
  csv:       'Operation: CSV import',
  yaml:      'Operation: YAML import',
}

// ── Props ────────────────────────────────────────────────────────────────────

export interface ConfirmationScreenProps {
  changeSetId: string
  applied: number
  source: 'wizard' | 'reshuffle' | 'csv' | 'yaml'
}

// ── Component ────────────────────────────────────────────────────────────────

export function ConfirmationScreen({ changeSetId, applied, source }: ConfirmationScreenProps) {
  const navigate = useNavigate()
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    void navigator.clipboard.writeText(changeSetId)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const heading = SOURCE_HEADINGS[source] ?? 'COMMITTED'
  const subline = SOURCE_SUBLINES[source] ?? `Operation: ${source}`

  return (
    <div className="confirmation-screen">
      {/* Success checkmark — --gruvax-success color applied via CSS */}
      <div className="confirmation-icon" aria-hidden="true">
        {/* Lucide CheckCircle */}
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="48" height="48"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
          <polyline points="22 4 12 14.01 9 11.01" />
        </svg>
      </div>

      {/* Heading — Barlow Condensed 900 24px ALL CAPS (--gruvax-text-display-md) */}
      <h1 className="confirmation-heading">{heading}</h1>

      {/* Operation sub-line — Space Grotesk 400 14px */}
      <p className="confirmation-subline">
        {`${subline} · ${applied} cube${applied !== 1 ? 's' : ''}`}
      </p>

      {/* change_set_id display */}
      <div className="confirmation-changeset">
        <span className="confirmation-changeset-label">Change set</span>
        <div className="confirmation-changeset-row">
          {/* Full UUID — DM Mono 500 16px */}
          <span className="confirmation-changeset-id">{changeSetId}</span>
          {/* Icon-only copy button — must carry aria-label (UI-SPEC checker flag) */}
          <button
            type="button"
            className="confirmation-copy-btn"
            aria-label="Copy change set ID"
            onClick={handleCopy}
          >
            {copied ? (
              /* Lucide Check — 1500ms swap, no animation per UI-SPEC Motion Contract */
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="14" height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <polyline points="20 6 9 17 4 12" />
              </svg>
            ) : (
              /* Lucide Copy */
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="14" height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* REVERT THIS CHANGE SET — links to history with highlight param (D-15) */}
      <button
        type="button"
        className="wizard-btn wizard-btn--outline confirmation-revert-btn"
        onClick={() => navigate(`/admin/history?highlight=${changeSetId}`)}
      >
        REVERT THIS CHANGE SET
      </button>

      {/* BACK TO CUBES — primary action */}
      <button
        type="button"
        className="wizard-btn wizard-btn--primary confirmation-cubes-btn"
        onClick={() => navigate('/admin/cubes')}
      >
        BACK TO CUBES
      </button>
    </div>
  )
}

// ── Route wrapper ─────────────────────────────────────────────────────────────
// Allows ConfirmationScreen to be rendered as a standalone route at
// /admin/wizard/done?change_set_id=...&applied=...&source=...
// The Wizard navigates here on successful commit.

export function ConfirmationRoute() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const changeSetId = searchParams.get('change_set_id') ?? ''
  const applied = parseInt(searchParams.get('applied') ?? '0', 10)
  const sourceRaw = searchParams.get('source') ?? 'wizard'
  const source = (['wizard', 'reshuffle', 'csv', 'yaml'].includes(sourceRaw)
    ? sourceRaw
    : 'wizard') as 'wizard' | 'reshuffle' | 'csv' | 'yaml'

  if (!changeSetId) {
    // No result — bounce back to wizard
    void navigate('/admin/wizard', { replace: true })
    return null
  }

  return (
    <ConfirmationScreen
      changeSetId={changeSetId}
      applied={applied}
      source={source}
    />
  )
}

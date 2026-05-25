/**
 * Wizard — two-mode cut-point walk for /admin/wizard (D-01, D-02, D-03, D-04).
 *
 * ONE wizard engine serves both setup (full fresh walk) and reshuffle (re-walk with
 * existing cut points pre-loaded).  The ?mode= query param or an existing reshuffleDraft
 * in the store determines which mode activates on mount.
 *
 * Entry choice (gap G1): when neither a ?mode= param nor a reshuffleDraft is present,
 * the route renders a mode-choice landing (WizardEntryChoice) instead of jumping
 * straight into setup.  Both CTA buttons navigate to the canonical URL with ?mode=
 * so there is ONE source of truth for mode and no drift vs. D-01.
 *
 * Design constraints (CLAUDE.md + 07-UI-SPEC.md):
 * - All colors via --gruvax-* CSS variables; NO hardcoded hex.
 * - All user-supplied strings via JSX {} interpolation; never innerHTML.
 * - RecordPickerSheet mounted per step as the per-step input (D-03); after its DB
 *   commit fires, the wizard reads the updated value via adminGetCubeBoundary.
 * - Cuts are cut points only (first_label/first_catalog/is_empty); no width overrides (D-02).
 * - Idempotency-Key generated once with crypto.randomUUID() and persisted in the draft
 *   before the network call so retries reuse the same key (Pattern 4).
 * - ONE atomic adminBulkSave(source='wizard'|'reshuffle') call commits all cuts (D-04).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import {
  adminBulkSave,
  adminGetCubeBoundary,
  adminGetCubes,
  validateBoundary,
} from '../../api/adminClient'
import type { CubeBoundaryEdit } from '../../api/types'
import { useAdminStore } from '../../state/adminStore'
import { LocatorHeader } from './LocatorHeader'
import { RecordPickerSheet } from './RecordPickerSheet'
import './admin.css'

// ── Types ────────────────────────────────────────────────────────────────────

type WizardMode = 'setup' | 'reshuffle'
type WizardPhase = 'walking' | 'review'

interface CutEntry {
  first_label: string | null
  first_catalog: string | null
  is_empty: boolean
}

interface CubeStep {
  unit_id: number
  row: number
  col: number
  first_label: string
  first_catalog: string
  is_empty: boolean
}

// ── Entry choice landing ──────────────────────────────────────────────────────

/**
 * WizardEntryChoice — shown when /admin/wizard is visited with no ?mode= param and
 * no in-progress reshuffleDraft.  Both buttons navigate to the canonical ?mode= URL
 * so the wizard engine resolves mode from one place only (D-01).
 */
function WizardEntryChoice() {
  const navigate = useNavigate()

  return (
    <div className="wizard-route wizard-entry">
      <h1 className="wizard-entry-heading">{'WIZARD'}</h1>
      <p className="wizard-entry-body">
        {'Choose how you want to update your cube boundaries. Set up from scratch if this is your first time, or run a reshuffle to re-walk existing shelves after a haul.'}
      </p>
      <div className="wizard-entry-actions">
        <button
          type="button"
          className="wizard-btn wizard-btn--primary"
          onClick={() => { void navigate('/admin/wizard?mode=setup') }}
        >
          {'START SETUP WIZARD'}
        </button>
        <button
          type="button"
          className="wizard-btn wizard-btn--outline"
          onClick={() => { void navigate('/admin/wizard?mode=reshuffle') }}
        >
          {'START RESHUFFLE'}
        </button>
      </div>
    </div>
  )
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function stepKey(step: { unit_id: number; row: number; col: number }): string {
  return `${step.unit_id}/${step.row}/${step.col}`
}

function buildUpdates(
  steps: CubeStep[],
  cuts: Record<string, CutEntry>,
): CubeBoundaryEdit[] {
  return steps.map((step) => {
    const key = stepKey(step)
    const cut = cuts[key]
    return {
      unit_id: step.unit_id,
      row: step.row,
      col: step.col,
      first_label: cut?.first_label ?? '',
      first_catalog: cut?.first_catalog ?? '',
      last_label: '',
      last_catalog: '',
      is_empty: cut?.is_empty ?? false,
    }
  })
}

// ── Wizard outer (entry gate) ─────────────────────────────────────────────────

/**
 * Wizard — exported component.  Renders the mode-choice landing when neither a
 * ?mode= query param nor a reshuffleDraft is present (gap G1); otherwise renders
 * the full wizard walk engine.  Splitting into outer + inner ensures all hooks in
 * WizardWalk are always called (React Rules of Hooks).
 */
export function Wizard() {
  const [searchParams] = useSearchParams()
  const { reshuffleDraft } = useAdminStore()

  const modeParam = searchParams.get('mode')
  if (!reshuffleDraft && !modeParam) {
    return <WizardEntryChoice />
  }

  return <WizardWalk />
}

// ── Wizard walk engine ────────────────────────────────────────────────────────

function WizardWalk() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { reshuffleDraft, setReshuffleDraft } = useAdminStore()

  // Determine mode from draft presence or ?mode= param
  const [mode] = useState<WizardMode>(() => {
    if (reshuffleDraft) return 'reshuffle'
    return searchParams.get('mode') === 'reshuffle' ? 'reshuffle' : 'setup'
  })

  const [phase, setPhase] = useState<WizardPhase>('walking')
  const [currentStepIndex, setCurrentStepIndex] = useState<number>(() => {
    if (reshuffleDraft) return Math.max(reshuffleDraft.completedSteps, 0)
    return 0
  })
  const [cuts, setCuts] = useState<Record<string, CutEntry>>(() => {
    return reshuffleDraft?.cuts ?? {}
  })
  const [showPicker, setShowPicker] = useState(false)
  const [validateErrors, setValidateErrors] = useState<string[]>([])
  const [commitError, setCommitError] = useState('')
  const [isCommitting, setIsCommitting] = useState(false)

  // Idempotency key — generated once, persisted in draft before network call (Pattern 4)
  const idempotencyKey = useRef<string>(
    reshuffleDraft?.idempotencyKey ?? crypto.randomUUID(),
  )
  const draftStartedAt = useRef<string>(
    reshuffleDraft?.startedAt ?? new Date().toISOString(),
  )
  const idempKeyPersisted = useRef(false)

  // ── Fetch cube list to build step sequence ────────────────────────────────
  const { data: cubesData, isLoading: cubesLoading } = useQuery({
    queryKey: ['admin', 'cubes'],
    queryFn: adminGetCubes,
    staleTime: 30_000,
  })

  const steps = useMemo<CubeStep[]>(() => {
    if (!cubesData) return []
    return [...cubesData.cubes].sort((a, b) => {
      if (a.unit_id !== b.unit_id) return a.unit_id - b.unit_id
      if (a.row !== b.row) return a.row - b.row
      return a.col - b.col
    })
  }, [cubesData])

  const totalSteps = steps.length
  const currentStep = steps[currentStepIndex] ?? null
  const isLastStep = currentStepIndex === totalSteps - 1
  const isReviewPhase = phase === 'review'

  // ── Pre-load existing cut points in reshuffle mode ────────────────────────
  useEffect(() => {
    if (mode === 'reshuffle' && cubesData && Object.keys(cuts).length === 0 && !reshuffleDraft) {
      const preloaded: Record<string, CutEntry> = {}
      for (const cube of cubesData.cubes) {
        preloaded[stepKey(cube)] = {
          first_label: cube.first_label,
          first_catalog: cube.first_catalog,
          is_empty: cube.is_empty,
        }
      }
      setCuts(preloaded)
    }
  }, [mode, cubesData, cuts, reshuffleDraft])

  // Persist idempotency key into draft on first render in reshuffle mode (Pattern 4)
  useEffect(() => {
    if (mode === 'reshuffle' && !idempKeyPersisted.current && totalSteps > 0) {
      idempKeyPersisted.current = true
      setReshuffleDraft({
        mode: 'reshuffle',
        completedSteps: currentStepIndex,
        cuts,
        idempotencyKey: idempotencyKey.current,
        startedAt: draftStartedAt.current,
      })
    }
  }, [mode, totalSteps, currentStepIndex, cuts, setReshuffleDraft])

  // ── Current step state ────────────────────────────────────────────────────
  const currentCut = currentStep ? (cuts[stepKey(currentStep)] ?? null) : null
  const currentStepDone = currentCut !== null && (
    currentCut.is_empty ||
    (!!currentCut.first_label && !!currentCut.first_catalog)
  )

  // ── Draft persistence helper (reshuffle mode only) ────────────────────────
  const persistDraft = useCallback(
    (updatedCuts: Record<string, CutEntry>, completedIdx: number) => {
      if (mode !== 'reshuffle') return
      setReshuffleDraft({
        mode: 'reshuffle',
        completedSteps: completedIdx,
        cuts: updatedCuts,
        idempotencyKey: idempotencyKey.current,
        startedAt: draftStartedAt.current,
      })
    },
    [mode, setReshuffleDraft],
  )

  // ── Step navigation ───────────────────────────────────────────────────────
  function handleSkip() {
    if (!currentStep) return
    const key = stepKey(currentStep)
    const newCuts = { ...cuts, [key]: { first_label: null, first_catalog: null, is_empty: true } }
    setCuts(newCuts)
    if (mode === 'reshuffle') persistDraft(newCuts, currentStepIndex + 1)
    if (isLastStep) {
      setPhase('review')
    } else {
      setCurrentStepIndex((i) => i + 1)
    }
  }

  function handleBack() {
    if (currentStepIndex === 0) return
    setCurrentStepIndex((i) => i - 1)
    if (phase === 'review') setPhase('walking')
  }

  function handleNext() {
    if (!currentStepDone) return
    if (isLastStep) {
      setPhase('review')
      return
    }
    if (mode === 'reshuffle') persistDraft(cuts, currentStepIndex + 1)
    setCurrentStepIndex((i) => i + 1)
  }

  // ── RecordPickerSheet commit handler ──────────────────────────────────────
  // RecordPickerSheet (D-03) commits via setCutPoint (DB write).
  // After its onCommit fires, re-fetch the cube boundary to read the value
  // it wrote, then update local cuts for draft + final commit.
  async function handlePickerCommit() {
    setShowPicker(false)
    if (!currentStep) return
    try {
      const boundary = await adminGetCubeBoundary(
        currentStep.unit_id,
        currentStep.row,
        currentStep.col,
      )
      const key = stepKey(currentStep)
      const newCuts: Record<string, CutEntry> = {
        ...cuts,
        [key]: {
          first_label: boundary.first_label,
          first_catalog: boundary.first_catalog,
          is_empty: false,
        },
      }
      setCuts(newCuts)
      if (mode === 'reshuffle') persistDraft(newCuts, currentStepIndex)
    } catch {
      // Non-fatal — the picker already wrote to DB; local draft just won't
      // show the value until next render. The final commit will re-read
      // from the DB via the cubes query cache.
    }
  }

  // ── Review: validate proposed set ─────────────────────────────────────────
  async function handleValidate() {
    if (steps.length === 0) return
    setValidateErrors([])
    const updates = buildUpdates(steps, cuts)
    try {
      const result = await validateBoundary(updates)
      if (!result.valid) {
        const msgs = result.results
          .filter((r) => !r.valid)
          .map((r) => r.message ?? r.error ?? 'Validation error')
        setValidateErrors(msgs)
      }
    } catch {
      setValidateErrors([
        'Something went wrong checking your changes. Check your connection and try again.',
      ])
    }
  }

  // ── Commit ────────────────────────────────────────────────────────────────
  async function handleCommit() {
    setIsCommitting(true)
    setCommitError('')

    // Persist idempotency key into draft immediately before network call (Pattern 4)
    if (mode === 'reshuffle') {
      setReshuffleDraft({
        mode: 'reshuffle',
        completedSteps: totalSteps,
        cuts,
        idempotencyKey: idempotencyKey.current,
        startedAt: draftStartedAt.current,
      })
    }

    try {
      const updates = buildUpdates(steps, cuts)
      const source: 'wizard' | 'reshuffle' = mode === 'reshuffle' ? 'reshuffle' : 'wizard'
      const result = await adminBulkSave(updates, idempotencyKey.current, source)
      setReshuffleDraft(null)  // clear localStorage draft on success (D-07)
      // Navigate to confirmation with result encoded in query params
      void navigate(`/admin/wizard/done?change_set_id=${encodeURIComponent(result.change_set_id)}&applied=${result.applied}&source=${source}`)
    } catch {
      setCommitError(
        'Something went wrong checking your changes. Check your connection and try again.',
      )
      setIsCommitting(false)
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────
  if (cubesLoading) {
    return (
      <div className="wizard-route">
        <p className="wizard-loading" aria-live="polite">Loading cubes…</p>
      </div>
    )
  }

  if (steps.length === 0) {
    return (
      <div className="wizard-route">
        <p className="wizard-empty">No cubes found. Set up shelves before running the wizard.</p>
      </div>
    )
  }

  const step = currentStep!
  const shelfLetter = String.fromCharCode(64 + (step?.unit_id ?? 1))
  const shelfName = `SHELF ${shelfLetter}`
  const binNumber = currentStepIndex + 1
  const progressPct = totalSteps > 0 ? (currentStepIndex / totalSteps) * 100 : 0

  return (
    <div className="wizard-route">
      {/* Mode badge */}
      <div className="wizard-mode-badge" data-mode={mode}>
        {mode === 'setup' ? 'SETUP' : 'RESHUFFLE'}
      </div>

      {/* LocatorHeader + step counter */}
      <div className="wizard-locator-header">
        <LocatorHeader
          unitId={step.unit_id}
          row={step.row}
          col={step.col}
          shelfName={shelfName}
          binNumber={binNumber}
        />
        <span className="wizard-step-indicator">
          {`${shelfName} · STEP `}
          <span className="wizard-step-mono">{`${binNumber} / ${totalSteps}`}</span>
        </span>
      </div>

      {/* Progress bar */}
      <div
        className="wizard-progress-track"
        role="progressbar"
        aria-valuenow={currentStepIndex}
        aria-valuemin={0}
        aria-valuemax={totalSteps}
        aria-label={`Step ${binNumber} of ${totalSteps}`}
      >
        <div className="wizard-progress-fill" style={{ width: `${progressPct}%` }} />
      </div>

      {/* Review phase */}
      {isReviewPhase ? (
        <div className="wizard-review">
          <h2 className="wizard-review-heading">REVIEW &amp; COMMIT</h2>
          <p className="wizard-review-body">
            {`${Object.keys(cuts).length} of ${totalSteps} cubes configured. Validate and commit below.`}
          </p>

          {validateErrors.length > 0 && (
            <div className="wizard-validate-errors" role="alert">
              <ul className="wizard-error-list">
                {validateErrors.map((msg, i) => (
                  <li key={i} className="wizard-error-item">{msg}</li>
                ))}
              </ul>
            </div>
          )}

          <button
            type="button"
            className="wizard-btn wizard-btn--outline"
            onClick={() => { void handleValidate() }}
          >
            VALIDATE CHANGES
          </button>

          {commitError && (
            <p className="wizard-commit-error" role="alert">{commitError}</p>
          )}

          <button
            type="button"
            className="wizard-btn wizard-btn--primary"
            onClick={() => { void handleCommit() }}
            disabled={validateErrors.length > 0 || isCommitting}
            aria-busy={isCommitting}
          >
            {isCommitting ? 'COMMITTING…' : 'COMMIT ALL CHANGES'}
          </button>

          <button
            type="button"
            className="wizard-btn wizard-btn--ghost"
            onClick={() => { setPhase('walking') }}
            disabled={isCommitting}
          >
            ← BACK TO WALK
          </button>
        </div>
      ) : (
        <div className="wizard-step">
          {/* End-of-shelf info card (last step) */}
          {isLastStep && (
            <div className="wizard-last-step-info">
              {/* Right-pointing chevron */}
              <svg
                className="wizard-chevron-icon"
                xmlns="http://www.w3.org/2000/svg"
                width="16" height="16" viewBox="0 0 24 24"
                fill="none" stroke="currentColor"
                strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                aria-hidden="true"
              >
                <polyline points="9 18 15 12 9 6" />
              </svg>
              <p className="wizard-last-step-text">
                This is the last bin. Everything in your collection from this point forward will
                be shelved here.
              </p>
            </div>
          )}

          <p className="wizard-step-question">
            {'What\'s the first record in this bin?'}
          </p>

          {/* Record card — shows current cut or picker trigger */}
          <div className="wizard-record-card">
            {currentCut && currentCut.is_empty ? (
              <div className="wizard-record-empty-chip">EMPTY — SKIP</div>
            ) : currentCut && currentCut.first_label ? (
              <div className="wizard-record-filled">
                <div className="wizard-record-text">
                  <span className="wizard-record-label">{currentCut.first_label}</span>
                  <span className="wizard-record-catalog">{currentCut.first_catalog}</span>
                </div>
                <button
                  type="button"
                  className="wizard-record-clear-btn"
                  aria-label="Clear selected record"
                  onClick={() => {
                    if (!currentStep) return
                    const key = stepKey(currentStep)
                    const newCuts = { ...cuts }
                    delete newCuts[key]
                    setCuts(newCuts)
                  }}
                >
                  {/* Lucide X */}
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14"
                       viewBox="0 0 24 24" fill="none" stroke="currentColor"
                       strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                       aria-hidden="true">
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </div>
            ) : (
              <button
                type="button"
                className="wizard-btn wizard-btn--outline wizard-pick-btn"
                onClick={() => setShowPicker(true)}
              >
                PICK A RECORD
              </button>
            )}
          </div>

          {/* Skip control (D-03) */}
          <button
            type="button"
            className="wizard-btn wizard-btn--outline wizard-skip-btn"
            onClick={handleSkip}
          >
            THIS BIN IS EMPTY / SKIP
          </button>

          {/* Back / Next navigation */}
          <div className="wizard-nav-row">
            <button
              type="button"
              className="wizard-btn wizard-btn--outline wizard-back-btn"
              onClick={handleBack}
              disabled={currentStepIndex === 0}
              aria-disabled={currentStepIndex === 0}
            >
              ← BACK
            </button>
            <button
              type="button"
              className="wizard-btn wizard-btn--primary wizard-next-btn"
              onClick={handleNext}
              disabled={!currentStepDone}
              aria-disabled={!currentStepDone}
            >
              {isLastStep ? 'REVIEW & COMMIT' : 'NEXT →'}
            </button>
          </div>
        </div>
      )}

      {/* RecordPickerSheet — per-step input (D-03, reused without modification) */}
      {showPicker && currentStep && (
        <RecordPickerSheet
          mode="edit"
          unitId={currentStep.unit_id}
          row={currentStep.row}
          col={currentStep.col}
          onCommit={() => { void handlePickerCommit() }}
          onCancel={() => setShowPicker(false)}
        />
      )}
    </div>
  )
}

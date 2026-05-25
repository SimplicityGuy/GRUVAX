/**
 * Import — /admin/import route (ADMN-05, D-08, D-11, SC2, BAK-01).
 *
 * Full implementation replacing the 07-04 stub.
 *
 * Flow: file drop/upload → dry_run preview (no write) → per-row errors with
 * did-you-mean chips → partial-import warning → affected-cubes diff preview
 * (mini-Kallax at 40px cells) → COMMIT IMPORT gated until zero errors →
 * real atomic commit → ConfirmationScreen with change_set_id + Revert tap (D-15).
 *
 * Design constraints (CLAUDE.md + 07-UI-SPEC.md):
 * - All colors via --gruvax-* tokens; NO hardcoded hex.
 * - All user-supplied strings via JSX {} interpolation; NEVER innerHTML.
 * - Movement counts MUST be suffixed "(approx.)" when non-zero (Pitfall 5).
 * - Partial-import warning MUST show when file cube count < total cubes (Pitfall 3).
 * - COMMIT IMPORT always visible, disabled (aria-disabled) until zero errors.
 *
 * G2/D-11 contract:
 * - runValidation calls uploadImportBoundaries with dryRun=true → preview with NO write.
 * - handleCommit calls uploadImportBoundaries with dryRun=false → atomic commit.
 * - B1: runValidation NEVER assigns commitResult (the field is removed from ImportState).
 *   The dry_run preview mints no change_set_id; storing a "pre-committed" result was
 *   the exact no-op bug (T-0708-NOOP-COMMIT). handleCommit always posts for real.
 * - W4: handleCommit always reaches the real uploadImportBoundaries(file, key, false)
 *   call — it is NEVER short-circuited by an all-errors-fixed check.
 * - W6: the 4xx error path reads err.body (the BulkSaveError parsed JSON) and feeds
 *   it to parseServerErrors + parseDiff without re-parsing a stringified message.
 */

import { useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import {
  uploadImportBoundaries,
  BulkSaveError,
} from '../../api/adminClient'
import './admin.css'

// ── Types ─────────────────────────────────────────────────────────────────────

interface NearMiss {
  label: string
  catalog: string
}

interface ImportError {
  row: number
  type: 'phantom_boundary' | 'contiguity_violation' | string
  first_label: string
  first_catalog: string
  message: string
  near_misses: NearMiss[]
  /** Whether this error has been fixed by applying a near-miss suggestion */
  fixed: boolean
  /** The suggestion that was applied (if any) */
  appliedSuggestion: NearMiss | null
}

interface DiffCube {
  unit_id: number
  row: number
  col: number
  delta: number
  willBeEmpty: boolean
}

type ImportPhase = 'idle' | 'validating' | 'validated' | 'committing' | 'done' | 'error'

interface ImportState {
  phase: ImportPhase
  file: File | null
  filename: string
  fileSize: number
  errors: ImportError[]
  diff: DiffCube[]
  totalCubes: number
  fileCubeCount: number
  commitError: string
  /** Cleared on each new file selection. Only set inside handleCommit (non-dry-run).
   *  Never set from runValidation (B1: dry_run mints no change_set_id). */
  idempotencyKey: string | null
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/**
 * Parse server 400 error response into ImportError items.
 * The import endpoint returns either:
 *   - {type, message, near_misses, row} for a single phantom/contiguity error
 *   - {errors: [...]} for bulk row errors
 */
function parseServerErrors(body: Record<string, unknown>): ImportError[] {
  // If the server gives a flat error (single phantom / contiguity)
  if (typeof body.type === 'string' && !Array.isArray(body.errors)) {
    const nearMisses: NearMiss[] = []
    if (Array.isArray(body.near_misses)) {
      for (const nm of body.near_misses as Record<string, unknown>[]) {
        if (typeof nm.label === 'string' && typeof nm.catalog === 'string') {
          nearMisses.push({ label: nm.label, catalog: nm.catalog })
        } else if (typeof nm.label === 'string' && typeof nm.catalog_number === 'string') {
          nearMisses.push({ label: nm.label, catalog: nm.catalog_number })
        }
      }
    }
    return [{
      row: typeof body.row === 'number' ? body.row : 0,
      type: body.type as string,
      first_label: typeof body.first_label === 'string' ? body.first_label : '',
      first_catalog: typeof body.first_catalog === 'string' ? body.first_catalog : '',
      message: typeof body.message === 'string' ? body.message : 'Validation error.',
      near_misses: nearMisses,
      fixed: false,
      appliedSuggestion: null,
    }]
  }
  // Bulk errors list
  if (Array.isArray(body.errors)) {
    return (body.errors as Record<string, unknown>[]).map((e) => {
      const nearMisses: NearMiss[] = []
      if (Array.isArray(e.near_misses)) {
        for (const nm of e.near_misses as Record<string, unknown>[]) {
          if (typeof nm.label === 'string' && typeof nm.catalog === 'string') {
            nearMisses.push({ label: nm.label, catalog: nm.catalog })
          } else if (typeof nm.label === 'string' && typeof nm.catalog_number === 'string') {
            nearMisses.push({ label: nm.label, catalog: nm.catalog_number })
          }
        }
      }
      return {
        row: typeof e.row === 'number' ? e.row : 0,
        type: typeof e.type === 'string' ? e.type : 'unknown',
        first_label: typeof e.first_label === 'string' ? e.first_label : '',
        first_catalog: typeof e.first_catalog === 'string' ? e.first_catalog : '',
        message: typeof e.message === 'string' ? e.message : 'Validation error.',
        near_misses: nearMisses,
        fixed: false,
        appliedSuggestion: null,
      }
    })
  }
  return []
}

/** Parse diff preview from a 200 dry_run response (diff_preview + counts). */
function parseDiff(body: Record<string, unknown>): { diff: DiffCube[]; fileCubeCount: number; totalCubes: number } {
  const diff: DiffCube[] = []
  let fileCubeCount = 0
  let totalCubes = 0

  if (typeof body.file_cube_count === 'number') fileCubeCount = body.file_cube_count
  if (typeof body.total_cubes === 'number') totalCubes = body.total_cubes

  if (Array.isArray(body.diff_preview)) {
    for (const d of body.diff_preview as Record<string, unknown>[]) {
      diff.push({
        unit_id: typeof d.unit_id === 'number' ? d.unit_id : 0,
        row: typeof d.row === 'number' ? d.row : 0,
        col: typeof d.col === 'number' ? d.col : 0,
        delta: typeof d.delta === 'number' ? d.delta : 0,
        willBeEmpty: d.will_be_empty === true,
      })
    }
  }
  return { diff, fileCubeCount, totalCubes }
}

// ── Diff mini-grid component ──────────────────────────────────────────────────

interface DiffGridProps {
  diff: DiffCube[]
  fileCubeCount: number
  totalCubes: number
}

function DiffGrid({ diff, fileCubeCount, totalCubes }: DiffGridProps) {
  if (diff.length === 0) return null

  // Group by unit_id
  const byUnit = new Map<number, DiffCube[]>()
  for (const cube of diff) {
    const arr = byUnit.get(cube.unit_id) ?? []
    arr.push(cube)
    byUnit.set(cube.unit_id, arr)
  }

  const changingCount = diff.filter((d) => !d.willBeEmpty && d.delta !== 0).length
  const unchangedCount = diff.filter((d) => d.delta === 0 && !d.willBeEmpty).length

  return (
    <div className="import-diff-section">
      <h2 className="import-section-heading">AFFECTED CUBES</h2>
      <p className="import-diff-summary">
        {changingCount} cube{changingCount !== 1 ? 's' : ''} changing
        {' · '}
        {unchangedCount} cube{unchangedCount !== 1 ? 's' : ''} unchanged
      </p>

      {Array.from(byUnit.entries()).map(([unitId, cubes]) => (
        <div key={unitId} className="import-diff-unit">
          <div className="import-diff-grid">
            {Array.from({ length: 4 }, (_, r) =>
              Array.from({ length: 4 }, (_, c) => {
                const cube = cubes.find((d) => d.row === r && d.col === c)
                let cellClass = 'import-diff-cell'
                if (cube) {
                  if (cube.willBeEmpty) {
                    cellClass += ' import-diff-cell--empty'
                  } else if (cube.delta !== 0) {
                    cellClass += ' import-diff-cell--changing'
                  }
                }
                return (
                  <div key={`${r}-${c}`} className={cellClass}>
                    {cube && cube.delta !== 0 && !cube.willBeEmpty && (
                      <span className="import-diff-count">
                        {cube.delta > 0 ? '+' : ''}{cube.delta} (approx.)
                      </span>
                    )}
                  </div>
                )
              }),
            )}
          </div>
        </div>
      ))}

      {totalCubes > 0 && fileCubeCount < totalCubes && (
        <div className="import-partial-warning" role="alert">
          <span className="import-partial-warning-icon" aria-hidden="true">
            {/* Lucide AlertTriangle */}
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
                 fill="none" stroke="currentColor" strokeWidth="2"
                 strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
          </span>
          {`This file defines ${fileCubeCount} cubes. The remaining ${totalCubes - fileCubeCount} cubes will be set to empty after import.`}
        </div>
      )}
    </div>
  )
}

// ── Error card component ──────────────────────────────────────────────────────

interface ErrorCardProps {
  error: ImportError
  index: number
  onApplySuggestion: (index: number, suggestion: NearMiss) => void
}

function ErrorCard({ error, index, onApplySuggestion }: ErrorCardProps) {
  const isContiguity = error.type === 'contiguity_violation'
  const cardClass = `import-error-card${error.fixed ? ' import-error-card--fixed' : ''}`

  return (
    <div className={cardClass} data-error-type={error.type}>
      <div className="import-error-header">
        <span className="import-error-row">
          {error.row > 0 ? `ROW ${error.row}` : 'ROW —'}
        </span>
        <span className={`import-error-badge${error.fixed ? ' import-error-badge--fixed' : ''}`}>
          {error.fixed ? 'FIXED' : isContiguity ? 'CONTIGUITY ERROR' : 'ERROR'}
        </span>
      </div>

      {!isContiguity && error.first_label && (
        <p className="import-error-body">
          {`"${error.first_label}" · "${error.first_catalog}" — not found in your collection.`}
        </p>
      )}

      {isContiguity && (
        <p className="import-error-body">
          {error.message || `${error.first_label} would be split across non-adjacent bins. Adjust this cut point to keep ${error.first_label} in one run.`}
        </p>
      )}

      {!error.fixed && !isContiguity && error.near_misses.length > 0 && (
        <div className="import-suggestion-row">
          <span className="import-suggestion-label">Did you mean?</span>
          <div className="import-suggestion-chips">
            {error.near_misses.map((miss) => (
              <button
                key={`${miss.label}|${miss.catalog}`}
                type="button"
                className="import-suggestion-chip"
                onClick={() => onApplySuggestion(index, miss)}
              >
                {miss.label} {'·'} {miss.catalog}
              </button>
            ))}
          </div>
        </div>
      )}

      {error.fixed && error.appliedSuggestion && (
        <p className="import-error-applied">
          {`Applied: ${error.appliedSuggestion.label} · ${error.appliedSuggestion.catalog}`}
        </p>
      )}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function Import() {
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const dropZoneRef = useRef<HTMLDivElement>(null)

  const [state, setState] = useState<ImportState>({
    phase: 'idle',
    file: null,
    filename: '',
    fileSize: 0,
    errors: [],
    diff: [],
    totalCubes: 0,
    fileCubeCount: 0,
    commitError: '',
    idempotencyKey: null,
    // Note: commitResult is intentionally absent from ImportState (B1).
    // The dry_run preview mints no change_set_id; storing a pre-committed result
    // was the no-op bug (T-0708-NOOP-COMMIT). handleCommit always posts for real.
  })

  const [isDragging, setIsDragging] = useState(false)

  const activeErrors = state.errors.filter((e) => !e.fixed)
  const hasErrors = activeErrors.length > 0
  const canCommit = state.phase === 'validated' && !hasErrors && state.file !== null

  // ── File handling ───────────────────────────────────────────────────────────

  function handleFileSelect(file: File) {
    if (file.size > 100_000) {
      setState((prev) => ({
        ...prev,
        phase: 'error',
        commitError: 'File is too large. Maximum upload size is 100 KB.',
        file: null,
        filename: '',
        fileSize: 0,
      }))
      return
    }
    const ext = file.name.split('.').pop()?.toLowerCase()
    if (ext !== 'csv' && ext !== 'yaml' && ext !== 'yml') {
      setState((prev) => ({
        ...prev,
        phase: 'error',
        commitError: 'Unsupported file format. Please upload a .csv or .yaml file.',
        file: null,
        filename: '',
        fileSize: 0,
      }))
      return
    }

    setState((prev) => ({
      ...prev,
      file,
      filename: file.name,
      fileSize: file.size,
      phase: 'validating',
      errors: [],
      diff: [],
      commitError: '',
      idempotencyKey: null,
    }))

    // Run the dry_run preview — server validates + computes diff with NO write.
    void runValidation(file)
  }

  async function runValidation(file: File) {
    // Call the dry_run preview endpoint: POST /api/admin/import/boundaries?dry_run=true
    // This runs the full parse + validation pipeline server-side with NO DB write.
    // On 200: diff preview body {total_cubes, file_cube_count, diff_preview}.
    // On 400/422: validation error body (same shape as the commit path).
    //
    // B1 — NO-OP REGRESSION GUARD:
    // runValidation MUST NOT assign idempotencyKey from this dry_run call and
    // MUST NOT store any "commitResult". The dry_run preview mints no change_set_id.
    // The ONLY idempotencyKey assignment is inside handleCommit (non-dry-run path).
    try {
      const previewResult = await uploadImportBoundaries(file, null, /*dryRun*/ true)
      // 200 preview body — feed through parseDiff (same shape parseDiff already reads).
      // Cast via unknown first since BoundariesDryRunPreview is a typed interface.
      const previewBody = previewResult as unknown as Record<string, unknown>
      const { diff, fileCubeCount, totalCubes } = parseDiff(previewBody)
      setState((prev) => ({
        ...prev,
        phase: 'validated',
        errors: [],
        diff,
        fileCubeCount,
        totalCubes,
        commitError: '',
        // B1: do NOT assign idempotencyKey here. The commit will generate a fresh one.
      }))
    } catch (err) {
      if (err instanceof BulkSaveError) {
        if (err.status === 400 || err.status === 422) {
          // W6: read err.body (the full parsed JSON from BulkSaveError) — no re-parsing.
          // Feed the same body object to both parseServerErrors and parseDiff.
          const body = err.body
          const errors = parseServerErrors(body)
          if (errors.length > 0) {
            const { diff, fileCubeCount, totalCubes } = parseDiff(body)
            setState((prev) => ({
              ...prev,
              phase: 'validated',
              errors,
              diff,
              fileCubeCount,
              totalCubes,
              commitError: '',
            }))
            return
          }
          // Fallback: no structured errors parsed — show generic error from BulkSaveError fields
          const fallbackErrors: ImportError[] = [{
            row: 0,
            type: err.errorType ?? 'unknown',
            first_label: '',
            first_catalog: '',
            message: err.serverMessage ?? 'Validation error.',
            near_misses: [],
            fixed: false,
            appliedSuggestion: null,
          }]
          setState((prev) => ({
            ...prev,
            phase: 'validated',
            errors: fallbackErrors,
            diff: [],
            commitError: '',
          }))
        } else {
          setState((prev) => ({
            ...prev,
            phase: 'error',
            commitError: 'Import failed — check your connection and try again. Your collection has not changed.',
          }))
        }
      } else {
        setState((prev) => ({
          ...prev,
          phase: 'error',
          commitError: 'Import failed — check your connection and try again. Your collection has not changed.',
        }))
      }
    }
  }

  function handleClearFile() {
    setState({
      phase: 'idle',
      file: null,
      filename: '',
      fileSize: 0,
      errors: [],
      diff: [],
      totalCubes: 0,
      fileCubeCount: 0,
      commitError: '',
      idempotencyKey: null,
    })
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  // ── Drag-and-drop ───────────────────────────────────────────────────────────

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault()
    setIsDragging(true)
  }

  function handleDragLeave() {
    setIsDragging(false)
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFileSelect(file)
  }

  // ── Near-miss suggestion ────────────────────────────────────────────────────

  function applyMiss(index: number, suggestion: NearMiss) {
    setState((prev) => ({
      ...prev,
      errors: prev.errors.map((err, i) =>
        i === index
          ? { ...err, fixed: true, appliedSuggestion: suggestion }
          : err,
      ),
    }))
  }

  // ── Commit ──────────────────────────────────────────────────────────────────

  async function handleCommit() {
    if (!state.file || !canCommit) return

    // T-0708-NOOP-COMMIT + W4: The "skip re-post if we already have a commitResult"
    // branch is REMOVED. This is the real atomic commit — it ALWAYS posts.
    //
    // W4 — chip-fixed path still posts: handleCommit MUST always call the real
    // (non-dryRun) uploadImportBoundaries even when every error was chip-fixed.
    // Applying did-you-mean chips only flips local `fixed` flags to enable the
    // button; it does NOT pre-commit anything. The actual write always happens here.
    //
    // If the server still rejects (because file bytes were not actually edited),
    // surface the returned errors again rather than silently committing.

    const key = crypto.randomUUID()
    setState((prev) => ({ ...prev, phase: 'committing', idempotencyKey: key, commitError: '' }))
    try {
      const result = await uploadImportBoundaries(state.file, key, /*dryRun*/ false)
      // result is CommitResponse on the non-dry-run path
      const commitData = result as { change_set_id: string; applied: number; source?: string }
      const ext = state.filename.split('.').pop()?.toLowerCase()
      const source = ext === 'csv' ? 'csv' : 'yaml'
      void navigate(
        `/admin/wizard/done?change_set_id=${commitData.change_set_id}&applied=${commitData.applied}&source=${source}`,
      )
    } catch (err) {
      if (err instanceof BulkSaveError && (err.status === 400 || err.status === 422)) {
        // Server rejected the commit (e.g. chip-fixes did not change file bytes) —
        // surface the errors again so the user can edit the file directly.
        const body = err.body
        const errors = parseServerErrors(body)
        if (errors.length > 0) {
          const { diff, fileCubeCount, totalCubes } = parseDiff(body)
          setState((prev) => ({
            ...prev,
            phase: 'validated',
            errors,
            diff,
            fileCubeCount,
            totalCubes,
            commitError: '',
          }))
          return
        }
      }
      setState((prev) => ({
        ...prev,
        phase: 'error',
        commitError: 'Import failed — check your connection and try again. Your collection has not changed.',
      }))
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="import-page">
      {/* Page heading */}
      <header className="import-header">
        <h1 className="import-heading">IMPORT BOUNDARIES</h1>
        <p className="import-subheading">
          Upload a CSV or YAML file to begin. All cubes not in the file will be set to empty.
        </p>
      </header>

      {/* File upload zone — collapses to file chip after selection */}
      {state.file ? (
        <div className="import-file-chip">
          <span className="import-file-chip-icon" aria-hidden="true">
            {/* Lucide File */}
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
                 fill="none" stroke="currentColor" strokeWidth="2"
                 strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
              <polyline points="13 2 13 9 20 9" />
            </svg>
          </span>
          <span className="import-file-chip-name">{state.filename}</span>
          <span className="import-file-chip-size">{formatFileSize(state.fileSize)}</span>
          <button
            type="button"
            className="import-file-chip-clear"
            aria-label="Clear selected file"
            onClick={handleClearFile}
          >
            {/* Lucide X */}
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                 fill="none" stroke="currentColor" strokeWidth="2"
                 strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      ) : (
        <div
          ref={dropZoneRef}
          className={`import-drop-zone${isDragging ? ' import-drop-zone--drag-over' : ''}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          role="button"
          tabIndex={0}
          aria-label="Drop a file or tap to upload"
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') fileInputRef.current?.click() }}
        >
          {/* Lucide Upload icon */}
          <svg
            className="import-drop-zone-icon"
            xmlns="http://www.w3.org/2000/svg"
            width="24" height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <polyline points="16 16 12 12 8 16" />
            <line x1="12" y1="12" x2="12" y2="21" />
            <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3" />
          </svg>
          <span className="import-drop-zone-label">DROP A FILE OR TAP TO UPLOAD</span>
          <span className="import-drop-zone-hint">Accepts: .csv or .yaml</span>
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept=".csv,.yaml,.yml"
        className="import-file-input-hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) handleFileSelect(file)
        }}
        aria-hidden="true"
        tabIndex={-1}
      />

      {/* Validating state */}
      {state.phase === 'validating' && (
        <div className="import-validating" aria-live="polite">
          <span className="import-validating-spinner" aria-hidden="true" />
          Checking file…
        </div>
      )}

      {/* Per-row error list */}
      {state.errors.length > 0 && (
        <div className="import-error-list" aria-live="polite" aria-label="Import validation errors">
          <h2 className="import-section-heading">
            {activeErrors.length > 0
              ? `${activeErrors.length} error${activeErrors.length !== 1 ? 's' : ''} found`
              : 'All errors resolved'}
          </h2>
          {state.errors.map((err, i) => (
            <ErrorCard
              key={i}
              error={err}
              index={i}
              onApplySuggestion={applyMiss}
            />
          ))}
        </div>
      )}

      {/* Diff preview */}
      {(state.phase === 'validated' || state.phase === 'committing') && (
        <DiffGrid
          diff={state.diff}
          fileCubeCount={state.fileCubeCount}
          totalCubes={state.totalCubes}
        />
      )}

      {/* Partial-import warning (standalone, when no diff grid shown) */}
      {state.phase === 'validated' &&
        state.diff.length === 0 &&
        state.totalCubes > 0 &&
        state.fileCubeCount < state.totalCubes && (
          <div className="import-partial-warning" role="alert">
            <span className="import-partial-warning-icon" aria-hidden="true">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
                   fill="none" stroke="currentColor" strokeWidth="2"
                   strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
            </span>
            {`This file defines ${state.fileCubeCount} cubes. The remaining ${state.totalCubes - state.fileCubeCount} cubes will be set to empty after import.`}
          </div>
        )}

      {/* Commit error */}
      {state.commitError && (
        <p className="import-commit-error" role="alert">
          {state.commitError}
        </p>
      )}

      {/* COMMIT IMPORT — always visible, disabled until zero errors */}
      {state.phase !== 'idle' && (
        <button
          type="button"
          className={`import-commit-btn${canCommit ? ' import-commit-btn--enabled' : ''}`}
          onClick={() => { if (canCommit) void handleCommit() }}
          aria-disabled={!canCommit}
          disabled={!canCommit}
        >
          {state.phase === 'committing' ? (
            <span className="import-commit-spinner" aria-hidden="true" />
          ) : (
            'COMMIT IMPORT'
          )}
        </button>
      )}
    </div>
  )
}

/**
 * CubeEditor — per-cube boundary editor with two-step dependent autocomplete.
 *
 * Two-step autocomplete (D-06):
 *   1. Label field — typeahead from GET /api/admin/labels (v_collection only).
 *   2. Catalog# field — enabled only once a label is chosen; typeahead from
 *      GET /api/admin/labels/{label}/catalogs scoped to that label.
 *
 * Phantom handling (D-07):
 *   - POST /api/admin/cubes/validate (dry-run) returns phantom=true with
 *     near_misses when a value is not in v_collection.
 *   - Phantom values are shown as warning chips with "USE ANYWAY" force path.
 *   - force=True skips phantom check on PUT /boundary but NEVER skips comparator.
 *
 * Midpoint suggestion (D-08):
 *   - "Suggest midpoint" button calls POST /api/admin/cubes/suggest.
 *   - Result is a real record from index space (always in v_collection).
 *
 * On save:
 *   - Calls setPendingChangeSet to accumulate edits (no direct PUT here).
 *   - Pending changes committed in a later phase (plan 05).
 *
 * Design tokens only — no hardcoded hex.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import {
  adminGetCubeBoundary,
  getCatalogsForLabel,
  getDistinctLabels,
  suggestMidpoint,
  validateBoundary,
} from '../../api/adminClient'
import type { CatalogOption, NearMiss } from '../../api/types'
import { useAdminStore } from '../../state/adminStore'

interface BoundaryFields {
  labelFirst: string
  catalogFirst: string
  labelLast: string
  catalogLast: string
}

/** A phantom warning with its near-miss candidates. */
interface PhantomWarning {
  field: 'first' | 'last'
  label: string
  catalog: string
  nearMisses: NearMiss[]
}

/** Debounce a value by delayMs. */
function useDebounce<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(t)
  }, [value, delayMs])
  return debounced
}

/** Autocomplete dropdown for a text field. */
function Autocomplete({
  id,
  label,
  value,
  options,
  onChange,
  onSelect,
  disabled,
  placeholder,
}: {
  id: string
  label: string
  value: string
  options: string[]
  onChange: (v: string) => void
  onSelect: (v: string) => void
  disabled?: boolean
  placeholder?: string
}) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const filtered = useMemo(() => {
    const q = value.toLowerCase()
    return options.filter((o) => o.toLowerCase().includes(q)).slice(0, 20)
  }, [value, options])

  // Close on click outside
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  return (
    <div className="autocomplete-wrapper" ref={containerRef}>
      <label htmlFor={id} className="editor-field-label">
        {label}
      </label>
      <input
        id={id}
        ref={inputRef}
        type="text"
        className="editor-field-input"
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(e) => {
          onChange(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        autoComplete="off"
        aria-autocomplete="list"
        aria-expanded={open && filtered.length > 0}
        aria-controls={`${id}-listbox`}
      />
      {open && filtered.length > 0 && !disabled && (
        <ul
          id={`${id}-listbox`}
          role="listbox"
          className="autocomplete-listbox"
        >
          {filtered.map((opt) => (
            <li
              key={opt}
              role="option"
              aria-selected={opt === value}
              className={`autocomplete-option${opt === value ? ' autocomplete-option--selected' : ''}`}
              onMouseDown={(e) => {
                e.preventDefault() // prevent input blur before click
                onSelect(opt)
                setOpen(false)
              }}
            >
              {opt}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function CubeEditor() {
  const { unit, row, col } = useParams<{
    unit: string
    row: string
    col: string
  }>()
  const navigate = useNavigate()
  const { pendingChangeSet, setPendingChangeSet } = useAdminStore()

  const unitId = Number(unit)
  const rowNum = Number(row)
  const colNum = Number(col)

  // ── Server state ──────────────────────────────────────────────────────────

  const { data: boundary, isLoading: boundaryLoading } = useQuery({
    queryKey: ['admin', 'cube-boundary', unitId, rowNum, colNum],
    queryFn: () => adminGetCubeBoundary(unitId, rowNum, colNum),
  })

  const { data: labelsData } = useQuery({
    queryKey: ['admin', 'labels'],
    queryFn: getDistinctLabels,
    staleTime: 5 * 60_000,
  })

  // ── Local form state ──────────────────────────────────────────────────────

  const [fields, setFields] = useState<BoundaryFields>({
    labelFirst: '',
    catalogFirst: '',
    labelLast: '',
    catalogLast: '',
  })

  // Populated once boundary loads
  useEffect(() => {
    if (boundary) {
      setFields({
        labelFirst: boundary.label_first,
        catalogFirst: boundary.catalog_first,
        labelLast: boundary.label_last,
        catalogLast: boundary.catalog_last,
      })
    }
  }, [boundary])

  const [phantomWarnings, setPhantomWarnings] = useState<PhantomWarning[]>([])
  const [forceFirst, setForceFirst] = useState(false)
  const [forceLast, setForceLast] = useState(false)
  const [isValidating, setIsValidating] = useState(false)
  const [isSuggestLoading, setIsSuggestLoading] = useState(false)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

  // ── Catalog dropdowns (scoped to chosen labels) ───────────────────────────

  const { data: catalogsFirst } = useQuery({
    queryKey: ['admin', 'catalogs', fields.labelFirst],
    queryFn: () => getCatalogsForLabel(fields.labelFirst),
    enabled: fields.labelFirst.trim().length > 0,
    staleTime: 5 * 60_000,
  })

  const { data: catalogsLast } = useQuery({
    queryKey: ['admin', 'catalogs', fields.labelLast],
    queryFn: () => getCatalogsForLabel(fields.labelLast),
    enabled: fields.labelLast.trim().length > 0,
    staleTime: 5 * 60_000,
  })

  const labelOptions = useMemo(
    () => (labelsData ? labelsData.map((l) => l.label) : []),
    [labelsData],
  )

  const catalogFirstOptions = useMemo(
    () => (catalogsFirst ? catalogsFirst.map((c: CatalogOption) => c.catalog_number) : []),
    [catalogsFirst],
  )

  const catalogLastOptions = useMemo(
    () => (catalogsLast ? catalogsLast.map((c: CatalogOption) => c.catalog_number) : []),
    [catalogsLast],
  )

  // ── Validate (dry-run) ────────────────────────────────────────────────────

  const debouncedFields = useDebounce(fields, 600)

  const runValidation = useCallback(async (f: BoundaryFields) => {
    if (!f.labelFirst || !f.catalogFirst || !f.labelLast || !f.catalogLast) return

    setIsValidating(true)
    setPhantomWarnings([])

    try {
      const result = await validateBoundary([
        {
          unit_id: unitId,
          row: rowNum,
          col: colNum,
          label_first: f.labelFirst,
          catalog_first: f.catalogFirst,
          label_last: f.labelLast,
          catalog_last: f.catalogLast,
        },
      ])

      const warnings: PhantomWarning[] = []
      for (const item of result.results) {
        if (item.phantom) {
          // Determine which field triggered the phantom (heuristic: check first then last)
          warnings.push({
            field: 'first',
            label: f.labelFirst,
            catalog: f.catalogFirst,
            nearMisses: item.near_misses ?? [],
          })
        }
      }
      setPhantomWarnings(warnings)
    } catch {
      // Validation errors don't block editing
    } finally {
      setIsValidating(false)
    }
  }, [unitId, rowNum, colNum])

  useEffect(() => {
    if (
      debouncedFields.labelFirst &&
      debouncedFields.catalogFirst &&
      debouncedFields.labelLast &&
      debouncedFields.catalogLast
    ) {
      void runValidation(debouncedFields)
    }
  }, [debouncedFields, runValidation])

  // ── Suggest midpoint ──────────────────────────────────────────────────────

  async function handleSuggestMidpoint() {
    setIsSuggestLoading(true)
    setSaveError(null)
    try {
      const result = await suggestMidpoint(unitId, rowNum, colNum)
      if (result.suggestion) {
        // Apply suggestion to the "last" boundary fields
        setFields((prev) => ({
          ...prev,
          labelLast: result.suggestion!.label,
          catalogLast: result.suggestion!.catalog_number,
        }))
      } else {
        setSaveError('No midpoint suggestion available for this cube.')
      }
    } catch {
      setSaveError('Failed to fetch midpoint suggestion.')
    } finally {
      setIsSuggestLoading(false)
    }
  }

  // ── Add to pending change-set (no direct write endpoint called here) ───────

  function handleAddToPending() {
    setSaveMessage(null)
    setSaveError(null)

    if (!fields.labelFirst || !fields.catalogFirst || !fields.labelLast || !fields.catalogLast) {
      setSaveError('All four fields are required.')
      return
    }

    // Build the new edit
    const newEdit = {
      unit_id: unitId,
      row: rowNum,
      col: colNum,
      label_first: fields.labelFirst,
      catalog_first: fields.catalogFirst,
      label_last: fields.labelLast,
      catalog_last: fields.catalogLast,
    }

    // Merge into pending change-set
    const now = new Date().toISOString()
    const existing = pendingChangeSet

    if (existing) {
      // Replace existing edit for this cube if present
      const otherEdits = existing.edits.filter(
        (e) => !(e.unit_id === unitId && e.row === rowNum && e.col === colNum),
      )
      setPendingChangeSet({
        ...existing,
        edits: [...otherEdits, newEdit],
      })
    } else {
      setPendingChangeSet({
        id: crypto.randomUUID(),
        created_at: now,
        edits: [newEdit],
      })
    }

    setSaveMessage('Added to pending change-set.')
  }

  // ── Render helpers ────────────────────────────────────────────────────────

  const hasPhantomFirst = phantomWarnings.some((w) => w.field === 'first')
  const hasPhantomLast = phantomWarnings.some((w) => w.field === 'last')

  if (boundaryLoading) {
    return (
      <div className="cube-editor-loading" aria-live="polite">
        Loading boundary...
      </div>
    )
  }

  return (
    <div className="cube-editor">
      <header className="cube-editor-header">
        <button
          type="button"
          className="cube-editor-back"
          onClick={() => void navigate('/admin/cubes')}
          aria-label="Back to cubes grid"
        >
          ← CUBES
        </button>
        <h1 className="cube-editor-title">
          EDIT {unitId}/{rowNum}/{colNum}
        </h1>
      </header>

      <div className="cube-editor-body">
        {/* First boundary */}
        <section className="editor-boundary-section">
          <h2 className="editor-boundary-heading">FIRST RECORD</h2>

          <Autocomplete
            id="label-first"
            label="Label"
            value={fields.labelFirst}
            options={labelOptions}
            onChange={(v) => {
              setFields((prev) => ({ ...prev, labelFirst: v, catalogFirst: '' }))
              setForceFirst(false)
            }}
            onSelect={(v) => {
              setFields((prev) => ({ ...prev, labelFirst: v, catalogFirst: '' }))
              setForceFirst(false)
            }}
            placeholder="Label name"
          />

          <Autocomplete
            id="catalog-first"
            label="Catalog #"
            value={fields.catalogFirst}
            options={catalogFirstOptions}
            onChange={(v) => {
              setFields((prev) => ({ ...prev, catalogFirst: v }))
              setForceFirst(false)
            }}
            onSelect={(v) => {
              setFields((prev) => ({ ...prev, catalogFirst: v }))
              setForceFirst(false)
            }}
            disabled={fields.labelFirst.trim() === ''}
            placeholder={fields.labelFirst ? 'Catalog number' : 'Choose label first'}
          />

          {/* Phantom warning for first boundary */}
          {hasPhantomFirst && !forceFirst && (
            <div className="phantom-chip" role="alert">
              <span className="phantom-chip-icon" aria-hidden="true">!</span>
              <span className="phantom-chip-text">
                Not in collection — verify label/catalog.
              </span>
              {phantomWarnings
                .filter((w) => w.field === 'first')
                .flatMap((w) => w.nearMisses)
                .slice(0, 3)
                .map((nm) => (
                  <button
                    key={nm.release_id}
                    type="button"
                    className="near-miss-chip"
                    onClick={() => {
                      setFields((prev) => ({
                        ...prev,
                        labelFirst: nm.label,
                        catalogFirst: nm.catalog_number,
                      }))
                    }}
                  >
                    {nm.label} / {nm.catalog_number}
                  </button>
                ))}
              <button
                type="button"
                className="phantom-force-btn"
                onClick={() => setForceFirst(true)}
              >
                USE ANYWAY
              </button>
            </div>
          )}
          {hasPhantomFirst && forceFirst && (
            <p className="phantom-forced-note" role="status">
              Phantom value accepted — comparator still checked on save.
            </p>
          )}
        </section>

        {/* Last boundary */}
        <section className="editor-boundary-section">
          <h2 className="editor-boundary-heading">LAST RECORD</h2>

          <Autocomplete
            id="label-last"
            label="Label"
            value={fields.labelLast}
            options={labelOptions}
            onChange={(v) => {
              setFields((prev) => ({ ...prev, labelLast: v, catalogLast: '' }))
              setForceLast(false)
            }}
            onSelect={(v) => {
              setFields((prev) => ({ ...prev, labelLast: v, catalogLast: '' }))
              setForceLast(false)
            }}
            placeholder="Label name"
          />

          <Autocomplete
            id="catalog-last"
            label="Catalog #"
            value={fields.catalogLast}
            options={catalogLastOptions}
            onChange={(v) => {
              setFields((prev) => ({ ...prev, catalogLast: v }))
              setForceLast(false)
            }}
            onSelect={(v) => {
              setFields((prev) => ({ ...prev, catalogLast: v }))
              setForceLast(false)
            }}
            disabled={fields.labelLast.trim() === ''}
            placeholder={fields.labelLast ? 'Catalog number' : 'Choose label first'}
          />

          {/* Phantom warning for last boundary */}
          {hasPhantomLast && !forceLast && (
            <div className="phantom-chip" role="alert">
              <span className="phantom-chip-icon" aria-hidden="true">!</span>
              <span className="phantom-chip-text">
                Not in collection — verify label/catalog.
              </span>
              {phantomWarnings
                .filter((w) => w.field === 'last')
                .flatMap((w) => w.nearMisses)
                .slice(0, 3)
                .map((nm) => (
                  <button
                    key={nm.release_id}
                    type="button"
                    className="near-miss-chip"
                    onClick={() => {
                      setFields((prev) => ({
                        ...prev,
                        labelLast: nm.label,
                        catalogLast: nm.catalog_number,
                      }))
                    }}
                  >
                    {nm.label} / {nm.catalog_number}
                  </button>
                ))}
              <button
                type="button"
                className="phantom-force-btn"
                onClick={() => setForceLast(true)}
              >
                USE ANYWAY
              </button>
            </div>
          )}
          {hasPhantomLast && forceLast && (
            <p className="phantom-forced-note" role="status">
              Phantom value accepted — comparator still checked on save.
            </p>
          )}
        </section>

        {/* Suggest midpoint */}
        <div className="editor-suggest-row">
          <button
            type="button"
            className="editor-btn-secondary"
            onClick={() => void handleSuggestMidpoint()}
            disabled={isSuggestLoading}
          >
            {isSuggestLoading ? 'SUGGESTING...' : 'SUGGEST MIDPOINT'}
          </button>
          <span className="editor-suggest-hint">
            Fills last record with index-space midpoint.
          </span>
        </div>

        {/* Validation status */}
        {isValidating && (
          <p className="editor-status-validating" aria-live="polite">
            Validating...
          </p>
        )}

        {/* Add to pending change-set */}
        <div className="editor-actions">
          <button
            type="button"
            className="editor-btn-secondary"
            onClick={handleAddToPending}
            disabled={isValidating}
          >
            ADD TO PENDING
          </button>
        </div>

        {saveMessage && (
          <p className="editor-save-success" role="status">
            {saveMessage}
          </p>
        )}
        {saveError && (
          <p className="editor-save-error" role="alert">
            {saveError}
          </p>
        )}

        {/* Pending change-set summary + preview */}
        {pendingChangeSet && pendingChangeSet.edits.length > 0 && (
          <div className="editor-pending-summary">
            <span className="editor-pending-count">
              {pendingChangeSet.edits.length} pending edit
              {pendingChangeSet.edits.length !== 1 ? 's' : ''}
            </span>
            <button
              type="button"
              className="editor-btn-primary"
              onClick={() => void navigate('/admin/preview')}
            >
              PREVIEW CHANGES
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

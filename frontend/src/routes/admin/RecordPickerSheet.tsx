/**
 * RecordPickerSheet — shared slide-up bottom sheet for cut-point editing.
 *
 * Two entry modes (UI-SPEC §F):
 *   - "edit"   → "EDIT CUT POINT"          → calls setCutPoint on commit
 *   - "insert" → "INSERT CUT AFTER BIN {n}" → calls insertCut on commit
 *
 * Reuses the Phase 3 two-step label → catalog autocomplete and phantom
 * blocking machinery (extracted from Phase 3 per-cube editor).
 *
 * HARD CONSTRAINT (T-05-05-01, boundary-editing.md):
 * Label strings from the collection may contain arbitrary characters.
 * All user-supplied strings are assigned via textContent (React JSX), never
 * via innerHTML. The Autocomplete component renders only via JSX.
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'
import {
  BulkSaveError,
  getCatalogsForLabel,
  getDistinctLabels,
  insertCut,
  setCutPoint,
} from '../../api/adminClient'
import type { CatalogOption, NearMiss } from '../../api/types'
import type { InsertCutBody } from '../../api/cubeTypes'

export type RecordPickerMode = 'edit' | 'insert'

export interface RecordPickerSheetProps {
  mode: RecordPickerMode
  /** The bin being edited (unit_id, row, col — 0-based). */
  unitId: number
  row: number
  col: number
  /** For insert mode: display number of bin after which cut is inserted. */
  afterBinDisplay?: number
  /** Called with updated segment list on successful commit. */
  onCommit: (updatedSegments?: unknown) => void
  /** Called when sheet is dismissed without commit. */
  onCancel: () => void
}

/** Debounce helper. */
function useDebounce<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(t)
  }, [value, delayMs])
  return debounced
}

/** Autocomplete dropdown for a single field. */
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

  const filtered = useMemo(() => {
    const q = value.toLowerCase()
    return options.filter((o) => o.toLowerCase().includes(q)).slice(0, 20)
  }, [value, options])

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
                e.preventDefault()
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

export function RecordPickerSheet({
  mode,
  unitId,
  row,
  col,
  afterBinDisplay,
  onCommit,
  onCancel,
}: RecordPickerSheetProps) {
  const [labelValue, setLabelValue] = useState('')
  const [catalogValue, setCatalogValue] = useState('')
  const [forcePhantom, setForcePhantom] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  // Two-step autocomplete
  const { data: labelsData } = useQuery({
    queryKey: ['admin', 'labels'],
    queryFn: getDistinctLabels,
    staleTime: 5 * 60_000,
  })

  const { data: catalogsData } = useQuery({
    queryKey: ['admin', 'catalogs', labelValue],
    queryFn: () => getCatalogsForLabel(labelValue),
    enabled: labelValue.trim().length > 0,
    staleTime: 5 * 60_000,
  })

  const labelOptions = useMemo(
    () => (labelsData ? labelsData.map((l) => l.label) : []),
    [labelsData],
  )

  const catalogOptions = useMemo(
    () => (catalogsData ? catalogsData.map((c: CatalogOption) => c.catalog_number) : []),
    [catalogsData],
  )

  // Phantom detection: derived state — no setState needed.
  const debouncedCatalog = useDebounce(catalogValue, 600)
  const debouncedLabel = useDebounce(labelValue, 600)

  const { phantom, nearMisses } = useMemo(() => {
    if (!debouncedLabel || !debouncedCatalog || catalogOptions.length === 0) {
      return { phantom: false, nearMisses: [] as NearMiss[] }
    }
    const exact = catalogOptions.includes(debouncedCatalog)
    if (exact) {
      return { phantom: false, nearMisses: [] as NearMiss[] }
    }
    const q = debouncedCatalog.toLowerCase()
    const misses: NearMiss[] = catalogOptions
      .filter((c) => c.toLowerCase().includes(q) || q.includes(c.toLowerCase()))
      .slice(0, 3)
      .map((c) => ({ release_id: 0, label: debouncedLabel, catalog_number: c, score: 0 }))
    return { phantom: true, nearMisses: misses }
  }, [debouncedLabel, debouncedCatalog, catalogOptions])

  const headingId = 'record-picker-heading'

  const heading =
    mode === 'edit'
      ? 'EDIT CUT POINT'
      : `INSERT CUT AFTER BIN ${afterBinDisplay ?? ''}`

  const commitLabel = mode === 'edit' ? 'SET CUT POINT' : 'INSERT CUT'

  async function handleCommit() {
    if (!labelValue.trim() || !catalogValue.trim()) {
      setSaveError('Label and catalog number are required.')
      return
    }
    if (phantom && !forcePhantom) {
      setSaveError('Resolve the phantom warning before saving, or tap USE ANYWAY.')
      return
    }

    setIsSaving(true)
    setSaveError(null)

    try {
      if (mode === 'edit') {
        await setCutPoint(unitId, row, col, {
          first_label: labelValue.trim(),
          first_catalog: catalogValue.trim(),
          force: forcePhantom || undefined,
        })
        onCommit()
      } else {
        const body: InsertCutBody = {
          after_unit_id: unitId,
          after_row: row,
          after_col: col,
          new_first_label: labelValue.trim(),
          new_first_catalog: catalogValue.trim(),
          force: forcePhantom || undefined,
        }
        const result = await insertCut(body)
        onCommit(result)
      }
    } catch (err) {
      // Both contiguity_error (SEG-05) and phantom_boundary share this 400 surfacing
      // path via BulkSaveError: the server's plain-language message is shown in the
      // .sheet-error block and the sheet stays open so the owner can reposition the cut.
      if (err instanceof BulkSaveError) {
        setSaveError(err.serverMessage ?? err.message)
        // Do NOT call onCommit or onCancel — sheet stays open for correction.
      } else {
        const msg = err instanceof Error ? err.message : 'Could not save — check your connection and try again.'
        setSaveError(msg)
      }
    } finally {
      setIsSaving(false)
    }
  }

  // Trap focus inside sheet (accessibility)
  const sheetRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = sheetRef.current
    if (!el) return
    const focusable = el.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    )
    if (focusable.length > 0) focusable[0].focus()
  }, [])

  return (
    <>
      {/* Scrim */}
      <div
        className="sheet-scrim"
        aria-hidden="true"
        onClick={onCancel}
      />

      {/* Bottom sheet */}
      <div
        ref={sheetRef}
        className="record-picker-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby={headingId}
      >
        {/* Drag pill */}
        <div className="sheet-drag-pill" aria-hidden="true" />

        <div className="sheet-body">
          <h2 id={headingId} className="sheet-heading">
            {heading}
          </h2>

          {/* Step 1: Label */}
          <Autocomplete
            id="picker-label"
            label="LABEL"
            value={labelValue}
            options={labelOptions}
            onChange={(v) => {
              setLabelValue(v)
              setCatalogValue('')
              setForcePhantom(false)
            }}
            onSelect={(v) => {
              setLabelValue(v)
              setCatalogValue('')
              setForcePhantom(false)
            }}
            placeholder="Label name"
          />

          {/* Step 2: Catalog — enabled only after label chosen */}
          <Autocomplete
            id="picker-catalog"
            label="CATALOG #"
            value={catalogValue}
            options={catalogOptions}
            onChange={(v) => {
              setCatalogValue(v)
              setForcePhantom(false)
            }}
            onSelect={(v) => {
              setCatalogValue(v)
              setForcePhantom(false)
            }}
            disabled={labelValue.trim() === ''}
            placeholder={labelValue ? 'Catalog number' : 'Choose label first'}
          />

          {/* Phantom warning */}
          {phantom && !forcePhantom && (
            <div className="phantom-chip" role="alert">
              <AlertTriangle size={16} className="phantom-chip-icon" aria-hidden="true" />
              <span className="phantom-chip-text">
                No match in collection. Did you mean one of these?
              </span>
              {nearMisses.map((nm) => (
                <button
                  key={nm.catalog_number}
                  type="button"
                  className="near-miss-chip"
                  onClick={() => {
                    setCatalogValue(nm.catalog_number)
                    setForcePhantom(false)
                  }}
                >
                  {nm.label} / {nm.catalog_number}
                </button>
              ))}
              <button
                type="button"
                className="phantom-force-btn"
                onClick={() => setForcePhantom(true)}
              >
                USE ANYWAY
              </button>
            </div>
          )}
          {phantom && forcePhantom && (
            <p className="phantom-forced-note" role="status">
              Phantom value accepted — comparator still checked on save.
            </p>
          )}

          {saveError && (
            <p className="sheet-error" role="alert">
              {saveError}
            </p>
          )}

          {/* Actions */}
          <div className="sheet-actions">
            <button
              type="button"
              className="editor-btn-primary sheet-commit-btn"
              onClick={() => void handleCommit()}
              disabled={isSaving || !labelValue.trim() || !catalogValue.trim()}
              aria-busy={isSaving}
            >
              {isSaving ? 'SAVING…' : commitLabel}
            </button>
            <button
              type="button"
              className="sheet-cancel-btn"
              onClick={onCancel}
              disabled={isSaving}
            >
              CANCEL
            </button>
          </div>
        </div>
      </div>
    </>
  )
}

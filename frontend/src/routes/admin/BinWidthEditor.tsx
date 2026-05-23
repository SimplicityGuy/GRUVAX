/**
 * BinWidthEditor — focused single-bin segment width editor (faithful port of sketch 001 Variant A).
 *
 * Route: /admin/cubes/:unit/:row/:col
 * Nav flow: ShelfBinList → ✎ EDIT SEGMENTS → BinWidthEditor → back to ShelfBinList
 *
 * Screen structure (mirrors sketch 001 Variant A exactly):
 *   - Back nav ("← SHELF A") + title "SHELF A · BIN n"
 *   - LocatorHeader: mini Kallax 4×4 (this bin lit yellow), "SHELF A"
 *   - Sum-note: "{N} labels share this bin · widths always total 100%"
 *   - Horizontal proportional strip (.strip) with SINGLE yellow pill handles (.handle .grip)
 *   - Hint: "Drag a yellow handle to set a physical-width override"
 *   - Continue caption when a label straddles: "↪ {LABEL} continues in BIN {n+1}"
 *   - White-card LEGEND (.leg-row): swatch, name, catalog range, AUTO/OVERRIDE chip + reset link
 *   - Actions: "↺ Reset to computed" (ghost) + "Save overrides"
 *
 * Drag logic: faithful port of attachDragH from sketch 001.
 *   - Pointer-capture; redistribute ONLY the two adjacent segments
 *   - Sum-conserving; clamp [left+MIN, right-MIN] with MIN=5%
 *   - Continuous drag — NO snapping
 *   - Build strip+handle DOM with el()+replaceChildren() — NEVER innerHTML
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { LocatorHeader } from './LocatorHeader'
import { getUnitSegments, setOverrides } from '../../api/adminClient'
import { shelfName, shelfLetter } from '../../lib/shelf'
import { useAdminStore } from '../../state/adminStore'
import { el } from '../../lib/dom'
import type { Segment } from '../../api/cubeTypes'

const ROWS = 4
const COLS = 4
const MIN = 0.05   // 5% minimum width per segment

/** Graduated-blue palette cycled by segment index. */
const PALETTE: Array<{ bg: string; fg: string }> = [
  { bg: 'var(--gruvax-blue)',        fg: 'var(--gruvax-white)' },
  { bg: 'var(--gruvax-blue-light)',  fg: 'var(--gruvax-blue-dark)' },
  { bg: 'var(--gruvax-blue-dark)',   fg: 'var(--gruvax-white)' },
  { bg: 'var(--gruvax-blue-darker)', fg: 'var(--gruvax-white)' },
]

function isOverridden(seg: Segment): boolean {
  return seg.is_override && Math.abs(seg.fraction - (seg.auto_fraction ?? seg.fraction)) > 0.005
}

/**
 * Largest-remainder (Hamilton) rounding: convert fractions (summing to ~1.0) into
 * integer percentages that sum to exactly 100, so the displayed numbers never read
 * 99 or 101 against the "widths always total 100%" promise.
 */
function roundPercents(fractions: number[]): number[] {
  if (fractions.length === 0) return []
  const raw = fractions.map((f) => f * 100)
  const floors = raw.map((v) => Math.floor(v))
  let deficit = 100 - floors.reduce((a, b) => a + b, 0)
  const result = [...floors]
  const byRemainder = raw
    .map((v, i) => ({ i, rem: v - floors[i] }))
    .sort((a, b) => b.rem - a.rem)
  for (let k = 0; k < byRemainder.length && deficit > 0; k++) {
    result[byRemainder[k].i] += 1
    deficit -= 1
  }
  return result
}

/**
 * Recompute applied fractions so the bin always sums to 1.0 (mirrors the backend
 * D-03 renormalization): overridden labels keep their fraction; the remaining width
 * is split among non-overridden labels proportionally by their auto (count-derived)
 * fraction. Used after dropping a single label's override.
 */
function renormalize(segs: Segment[]): Segment[] {
  const overrideSum = segs.filter((s) => s.is_override).reduce((a, s) => a + s.fraction, 0)
  const autoLabels = segs.filter((s) => !s.is_override)
  const autoSum = autoLabels.reduce((a, s) => a + s.auto_fraction, 0)
  const remainder = Math.max(0, 1 - overrideSum)
  return segs.map((s) =>
    s.is_override
      ? s
      : {
          ...s,
          fraction:
            autoSum > 0
              ? (s.auto_fraction / autoSum) * remainder
              : remainder / Math.max(1, autoLabels.length),
        },
  )
}

export function BinWidthEditor() {
  const { unit, row, col } = useParams<{ unit: string; row: string; col: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { pendingChangeSet, setPendingChangeSet } = useAdminStore()

  const unitId = Number(unit)
  const rowNum = Number(row)
  const colNum = Number(col)

  // 1-based bin display number (row-major)
  const binDisplay = rowNum * COLS + colNum + 1
  const shelfLtr = shelfLetter(unitId)
  const shelfDisplayName = shelfName(unitId)

  // ── Server data ──────────────────────────────────────────────────────────────
  const { data: segsData, isLoading } = useQuery({
    queryKey: ['admin', 'segments', unitId, rowNum, colNum],
    queryFn: () => getUnitSegments(unitId, rowNum, colNum),
    staleTime: 30_000,
  })

  // ── Local segment state (mutable for drag) ───────────────────────────────────
  const [segments, setSegments] = useState<Segment[]>([])
  const seededRef = useRef<Segment[] | null>(null)

  // Seed local state from server data (once per load)
  useEffect(() => {
    if (segsData?.segments && segsData.segments !== seededRef.current) {
      seededRef.current = segsData.segments
      setSegments(segsData.segments.map((s) => ({ ...s })))
    }
  }, [segsData])

  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveMsg, setSaveMsg] = useState<string | null>(null)

  // ── Strip DOM ref ────────────────────────────────────────────────────────────
  const stripWrapRef = useRef<HTMLDivElement>(null)
  // Mutable drag state — not in React state to avoid re-renders during drag
  const draggingSegs = useRef<Segment[]>([])

  // ── Stage override in pending change-set ────────────────────────────────────
  const stageOverride = useCallback(
    (updatedSegs: Segment[]) => {
      const now = new Date().toISOString()
      const edit = {
        unit_id: unitId,
        row: rowNum,
        col: colNum,
        first_label: '',
        first_catalog: '',
        last_label: '',
        last_catalog: '',
        segment_overrides: updatedSegs
          .filter((s) => s.is_override)
          .map((s) => ({ label: s.label, fraction: s.fraction })),
      }
      const existing = pendingChangeSet
      if (existing) {
        const others = existing.edits.filter(
          (e) => !(e.unit_id === unitId && e.row === rowNum && e.col === colNum),
        )
        setPendingChangeSet({ ...existing, edits: [...others, edit] })
      } else {
        setPendingChangeSet({ id: crypto.randomUUID(), created_at: now, edits: [edit] })
      }
    },
    [unitId, rowNum, colNum, pendingChangeSet, setPendingChangeSet],
  )

  // ── Render the strip + handles (pure DOM, no innerHTML, el() + replaceChildren) ──
  const renderStrip = useCallback((segs: Segment[]) => {
    const wrap = stripWrapRef.current
    if (!wrap) return

    const strip = wrap.querySelector<HTMLDivElement>('.bwe-strip')
    if (!strip) return

    // Remove old handles
    wrap.querySelectorAll('.bwe-handle').forEach((h) => h.remove())

    // Build segment divs
    const segNodes: Node[] = []
    const pcts = roundPercents(segs.map((s) => s.fraction)) // display integers sum to 100
    segs.forEach((seg, i) => {
      const pal = PALETTE[i % PALETTE.length]
      const showName = seg.fraction >= 0.16
      const segDiv = el('div', {
        className: `bwe-seg${seg.is_override ? ' bwe-seg--overridden' : ''}${seg.continues ? ' bwe-seg--continues' : ''}`,
        style: {
          width: `${(seg.fraction * 100).toFixed(3)}%`,
          background: pal.bg,
          color: pal.fg,
        },
      })

      if (showName) {
        segDiv.appendChild(
          el('span', { className: 'bwe-seg-name', textContent: seg.label.toUpperCase() }),
        )
      }
      segDiv.appendChild(
        el('span', { className: 'bwe-seg-pct', textContent: `${pcts[i]}%` }),
      )

      if (seg.continues) {
        segDiv.appendChild(
          el('span', { className: 'bwe-seg-continues-icon', textContent: '↪' }),
        )
      }

      segNodes.push(segDiv)
    })

    strip.replaceChildren(...segNodes)

    // Build drag handles between adjacent segments
    let cum = 0
    for (let i = 0; i < segs.length - 1; i++) {
      cum += segs[i].fraction
      const handle = el('div', {
        className: 'bwe-handle',
        style: { left: `${(cum * 100).toFixed(4)}%` },
      })
      handle.appendChild(el('div', { className: 'bwe-grip' }))
      // attachDragH is a hoisted function decl below; mutual recursion with renderStrip
      // eslint-disable-next-line react-hooks/immutability
      attachDragH(handle, i, strip)
      wrap.appendChild(handle)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Pointer-capture drag logic (faithful port of sketch 001 attachDragH) ────
  function attachDragH(handle: HTMLElement, idx: number, strip: HTMLElement) {
    handle.addEventListener('pointerdown', (e: PointerEvent) => {
      e.preventDefault()
      handle.classList.add('bwe-handle--dragging')
      handle.setPointerCapture(e.pointerId)

      const rect = strip.getBoundingClientRect()
      const segs = draggingSegs.current
      const left = segs.slice(0, idx).reduce((a, s) => a + s.fraction, 0)
      const right = left + segs[idx].fraction + segs[idx + 1].fraction

      const onMove = (ev: PointerEvent) => {
        let pos = (ev.clientX - rect.left) / rect.width
        pos = Math.max(left + MIN, Math.min(right - MIN, pos))
        draggingSegs.current[idx].fraction = pos - left
        draggingSegs.current[idx + 1].fraction = right - pos
        // Mark both as override during drag
        draggingSegs.current[idx].is_override = true
        draggingSegs.current[idx + 1].is_override = true
        renderStrip(draggingSegs.current)
        updateCaption(draggingSegs.current)
      }

      const onUp = () => {
        handle.classList.remove('bwe-handle--dragging')
        try { handle.releasePointerCapture(e.pointerId) } catch { /* ignore */ }
        document.removeEventListener('pointermove', onMove)
        document.removeEventListener('pointerup', onUp)
        // Commit drag result to React state
        const updated = draggingSegs.current.map((s) => ({ ...s }))
        setSegments(updated)
        updateLegend(updated)
      }

      document.addEventListener('pointermove', onMove)
      document.addEventListener('pointerup', onUp)
    })
  }

  // ── Caption ref (continue caption below strip) ───────────────────────────────
  const captionRef = useRef<HTMLDivElement>(null)

  function updateCaption(segs: Segment[]) {
    const cap = captionRef.current
    if (!cap) return
    const cont = segs.find((s) => s.continues)
    cap.replaceChildren()
    if (cont) {
      const label = el('span', { textContent: `↪ ${cont.label.toUpperCase()} continues in ` })
      const mono = el('span', {
        className: 'bwe-caption-mono',
        textContent: `BIN ${binDisplay + 1}`,
      })
      cap.appendChild(label)
      cap.appendChild(mono)
    }
  }

  // ── Legend ref ───────────────────────────────────────────────────────────────
  const legendRef = useRef<HTMLDivElement>(null)

  const updateLegend = useCallback((segs: Segment[]) => {
    const root = legendRef.current
    if (!root) return
    root.replaceChildren()

    // Largest-remainder rounding so both applied and auto displays sum to exactly 100
    const pcts = roundPercents(segs.map((s) => s.fraction))
    const autoPcts = roundPercents(segs.map((s) => s.auto_fraction ?? s.fraction))
    segs.forEach((seg, i) => {
      const pal = PALETTE[i % PALETTE.length]
      const ov = isOverridden(seg)
      const displayPct = pcts[i]
      const autoPct = autoPcts[i]

      // Swatch
      const swatch = el('span', {
        className: 'bwe-leg-swatch',
        style: { background: pal.bg },
      })

      // Main info
      const main = el('div', { className: 'bwe-leg-main' })
      const nm = el('div', { className: 'bwe-leg-nm', textContent: seg.label.toUpperCase() })
      if (seg.continues) {
        nm.appendChild(
          el('span', {
            style: { color: 'var(--gruvax-yellow-dark)' },
            textContent: ' ↪',
            title: 'continues in next bin',
          }),
        )
      }
      main.appendChild(nm)

      // Record count (honesty rule: counts come from row-counting v_collection, not catalog math)
      const rng = el('div', {
        className: 'bwe-leg-rng',
        textContent: `${seg.segment_count} record${seg.segment_count !== 1 ? 's' : ''}${seg.continues ? '  ·  spans into next bin' : ''}`,
      })
      main.appendChild(rng)

      // Chip + reset
      if (ov) {
        const chip = el('span', { className: 'bwe-chip bwe-chip--set' })
        chip.appendChild(el('span', { className: 'bwe-chip-dot' }))
        chip.appendChild(
          document.createTextNode(`OVERRIDE ${displayPct}% · auto was ${autoPct}%`),
        )
        main.appendChild(chip)

        const reset = el('button', {
          className: 'bwe-reset-link',
          textContent: `reset to ${autoPct}%`,
          // resetOne is a hoisted function decl below; mutual recursion with updateLegend
          // eslint-disable-next-line react-hooks/immutability
          onClick: () => resetOne(seg.label),
        })
        main.appendChild(reset)
      } else {
        const chip = el('span', { className: 'bwe-chip bwe-chip--auto' })
        chip.appendChild(el('span', { className: 'bwe-chip-dot' }))
        chip.appendChild(document.createTextNode(`AUTO · ${autoPct}% from row counts`))
        main.appendChild(chip)
      }

      // Percentage display
      const pct = el('div', { className: 'bwe-leg-pct' })
      pct.appendChild(document.createTextNode(String(displayPct)))
      pct.appendChild(el('span', { style: { fontSize: '11px' }, textContent: '%' }))

      const row = el('div', { className: 'bwe-leg-row' })
      row.appendChild(swatch)
      row.appendChild(main)
      row.appendChild(pct)
      root.appendChild(row)
    })
  }, [binDisplay]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Reset helpers ────────────────────────────────────────────────────────────
  function resetOne(label: string) {
    setSegments((prev) => {
      // Drop this label's override, then renormalize so the bin still sums to 100%.
      const cleared = prev.map((s) =>
        s.label === label ? { ...s, is_override: false } : { ...s },
      )
      const updated = renormalize(cleared)
      draggingSegs.current = updated.map((s) => ({ ...s }))
      renderStrip(updated)
      updateCaption(updated)
      updateLegend(updated)
      return updated
    })
  }

  function resetAll() {
    setSegments((prev) => {
      const updated = prev.map((s) => ({
        ...s,
        fraction: s.auto_fraction ?? s.fraction,
        is_override: false,
      }))
      draggingSegs.current = updated.map((s) => ({ ...s }))
      renderStrip(updated)
      updateCaption(updated)
      updateLegend(updated)
      return updated
    })
  }

  // ── Save overrides ───────────────────────────────────────────────────────────
  async function handleSave() {
    setIsSaving(true)
    setSaveError(null)
    setSaveMsg(null)
    try {
      const idempotencyKey = crypto.randomUUID()
      await setOverrides(
        unitId,
        rowNum,
        colNum,
        {
          overrides: segments.map((s) => ({
            label: s.label,
            fraction: s.is_override ? s.fraction : null,
          })),
        },
        idempotencyKey,
      )
      stageOverride(segments)
      const overrideCount = segments.filter(isOverridden).length
      setSaveMsg(
        overrideCount
          ? `Saved · ${overrideCount} override${overrideCount !== 1 ? 's' : ''} written`
          : 'Saved · all widths auto-computed',
      )
      void queryClient.invalidateQueries({ queryKey: ['admin', 'segments', unitId, rowNum, colNum] })
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Could not save overrides — try again.')
    } finally {
      setIsSaving(false)
    }
  }

  // ── Sync draggingSegs ref + re-render strip when segments state changes ──────
  useEffect(() => {
    draggingSegs.current = segments.map((s) => ({ ...s }))
    renderStrip(segments)
    updateCaption(segments)
    updateLegend(segments)
  }, [segments, renderStrip, updateLegend])

  // ── Summary line ─────────────────────────────────────────────────────────────
  const labelCount = segments.length

  if (isLoading) {
    return (
      <div className="cut-point-editor-loading" aria-live="polite">
        Loading segments…
      </div>
    )
  }

  return (
    <div className="bwe-screen">
      {/* Header — back + title */}
      <header className="bwe-header">
        <button
          type="button"
          className="bwe-back"
          onClick={() => void navigate(`/admin/cubes/${unitId}`)}
          aria-label={`Back to ${shelfDisplayName} bin list`}
        >
          ← SHELF {shelfLtr}
        </button>
        <h1 className="bwe-title">SHELF {shelfLtr} · BIN {binDisplay}</h1>
      </header>

      {/* Locator header (this bin lit yellow) */}
      <LocatorHeader
        unitId={unitId}
        row={rowNum}
        col={colNum}
        shelfName={shelfDisplayName}
        binNumber={binDisplay}
        rows={ROWS}
        cols={COLS}
      />

      {/* Sum note */}
      <p className="bwe-sum-note">
        {labelCount} label{labelCount !== 1 ? 's' : ''} share this bin · widths always total{' '}
        <b>100%</b>
      </p>

      {/* Segment strip wrapper (drag handles appended by renderStrip) */}
      <div className="bwe-strip-wrap" ref={stripWrapRef}>
        <div className="bwe-strip" aria-label="Segment proportions" />
      </div>

      {/* Continue caption */}
      <div className="bwe-continue-cap" ref={captionRef} />

      {/* Hint */}
      <p className="bwe-hint">Drag a yellow handle to set a physical-width override</p>

      {/* Legend */}
      <div className="bwe-legend" ref={legendRef} />

      {/* Status messages */}
      {saveMsg && (
        <p className="editor-save-success" role="status">{saveMsg}</p>
      )}
      {saveError && (
        <p className="editor-save-error" role="alert">{saveError}</p>
      )}

      {/* Actions */}
      <div className="bwe-actions">
        <button
          type="button"
          className="bwe-btn-ghost"
          onClick={resetAll}
          disabled={isSaving}
        >
          ↺ Reset to computed
        </button>
        <button
          type="button"
          className="bwe-btn-primary"
          onClick={() => void handleSave()}
          disabled={isSaving}
        >
          {isSaving ? 'Saving…' : 'Save overrides'}
        </button>
      </div>
    </div>
  )
}

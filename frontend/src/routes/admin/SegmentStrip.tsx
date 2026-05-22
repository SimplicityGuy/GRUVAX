/**
 * SegmentStrip — horizontal proportional bar representing one bin's label segments.
 *
 * Full variant (isReadOnly=false): 88px tall with draggable handles.
 * Mini variant (isReadOnly=true): 24px tall, read-only (no drag).
 *
 * HARD CONSTRAINT (T-05-05-01, boundary-editing.md):
 * Drag handle DOM is built with el() + strip.replaceChildren() — NEVER innerHTML.
 * Label strings from the collection may contain arbitrary characters; assigning
 * them via textContent (not innerHTML) is the XSS defense.
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 */

import { useEffect, useRef } from 'react'
import { el } from '../../lib/dom'
import type { Segment } from '../../api/cubeTypes'

export type { Segment }

export interface SegmentStripProps {
  segments: Segment[]
  /** Called when user drags a handle — provides the index and new fraction of segs[index]. */
  onDragSetOverride?: (index: number, newFraction: number) => void
  /** true = mini 24px read-only variant for bin-card list */
  isReadOnly?: boolean
}

/** Blue-family fill tokens cycled by segment index within each bin. */
const SEGMENT_FILL_TOKENS = [
  '--gruvax-blue',
  '--gruvax-blue-light',
  '--gruvax-blue-dark',
] as const

/** Text-on-fill tokens (parallel to SEGMENT_FILL_TOKENS). */
const SEGMENT_TEXT_TOKENS = [
  '--gruvax-white',
  '--gruvax-blue-dark',
  '--gruvax-white',
] as const

/** Sum fractions from index start (inclusive) to end (exclusive). */
function sumFractions(segs: Segment[], start: number, end: number): number {
  let acc = 0
  for (let i = start; i < end; i++) acc += segs[i]?.fraction ?? 0
  return acc
}

/** Minimum segment width as a fraction (5%). */
const MIN = 0.05

export function SegmentStrip({ segments, onDragSetOverride, isReadOnly = false }: SegmentStripProps) {
  const stripRef = useRef<HTMLDivElement>(null)
  // Mutable copy of fractions for drag computation — reset each render
  const draggingSegs = useRef<Segment[]>([])

  useEffect(() => {
    const strip = stripRef.current
    if (!strip) return

    // Keep a mutable reference for drag (avoids stale closure)
    draggingSegs.current = segments.map((s) => ({ ...s }))

    function renderAll(segs: Segment[]) {
      if (!strip) return
      const isFullSize = !isReadOnly
      const nodes: Node[] = []

      segs.forEach((seg, i) => {
        const fillToken = SEGMENT_FILL_TOKENS[i % SEGMENT_FILL_TOKENS.length]
        const textToken = SEGMENT_TEXT_TOKENS[i % SEGMENT_TEXT_TOKENS.length]
        const widthPct = (seg.fraction * 100).toFixed(3) + '%'

        const segDiv = el('div', {
          className: `seg-strip__segment${seg.continues ? ' seg-strip__segment--continues' : ''}${seg.isOverride ? ' seg-strip__segment--override' : ''}`,
          style: {
            width: widthPct,
            background: `var(${fillToken})`,
            color: `var(${textToken})`,
            transition: `width var(--gruvax-duration-fast) linear`,
          },
        })

        // Override accent bar (5px top for full, 3px for mini)
        if (seg.isOverride) {
          const accentHeight = isFullSize ? '5px' : '3px'
          const accentShadow = isFullSize ? 'var(--gruvax-shadow-led)' : 'none'
          const accent = el('div', {
            className: 'seg-strip__override-accent',
            style: {
              height: accentHeight,
              background: 'var(--gruvax-yellow)',
              boxShadow: accentShadow,
            },
          })
          segDiv.appendChild(accent)
        }

        // Label name on full-size strip (not on mini)
        if (isFullSize) {
          const labelName = el('span', {
            className: 'seg-strip__label',
            textContent: seg.label.toUpperCase(),
            'aria-hidden': 'true',
          })
          segDiv.appendChild(labelName)
        }

        nodes.push(segDiv)

        // Drag handle between this segment and the next (full-size + not read-only + not last)
        if (isFullSize && !isReadOnly && i < segs.length - 1 && onDragSetOverride) {
          const handle = el('div', {
            className: 'seg-strip__handle',
            role: 'slider',
            tabIndex: 0,
            'aria-label': `Drag boundary between ${segs[i].label} and ${segs[i + 1].label}`,
            'aria-valuemin': '5',
            'aria-valuemax': '95',
            'aria-valuenow': String(Math.round(seg.fraction * 100)),
          })

          const idx = i // closure capture
          handle.addEventListener('pointerdown', (ev: PointerEvent) => {
            ev.preventDefault()
            handle.setPointerCapture(ev.pointerId)
            const rect = strip.getBoundingClientRect()

            const left = sumFractions(draggingSegs.current, 0, idx)
            const right = sumFractions(draggingSegs.current, 0, idx + 2)

            const onMove = (moveEv: PointerEvent) => {
              let pos = (moveEv.clientX - rect.left) / rect.width
              pos = Math.max(left + MIN, Math.min(right - MIN, pos))
              draggingSegs.current[idx].fraction = pos - left
              draggingSegs.current[idx + 1].fraction = right - pos
              // Mark both as override during drag
              draggingSegs.current[idx].isOverride = true
              draggingSegs.current[idx + 1].isOverride = true
              renderAll(draggingSegs.current)
            }

            const onUp = () => {
              handle.removeEventListener('pointermove', onMove)
              handle.removeEventListener('pointerup', onUp)
              onDragSetOverride(idx, draggingSegs.current[idx].fraction)
            }

            handle.addEventListener('pointermove', onMove)
            handle.addEventListener('pointerup', onUp)
          })

          nodes.push(handle)
        }
      })

      strip.replaceChildren(...nodes)
    }

    renderAll(draggingSegs.current)
  }, [segments, isReadOnly, onDragSetOverride])

  const stripClass = isReadOnly ? 'seg-strip seg-strip--mini' : 'seg-strip seg-strip--full'

  return <div className={stripClass} ref={stripRef} aria-label="Segment proportions" />
}

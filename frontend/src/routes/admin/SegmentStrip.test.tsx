import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { Segment } from '../../api/cubeTypes'
import { SegmentStrip } from './SegmentStrip'

const segments: Segment[] = ['<img src=x>', 'LabelB'].map((label) => ({
  label,
  fraction: 0.5,
  auto_fraction: 0.5,
  continues: false,
  is_override: false,
  segment_count: 10,
}))
beforeEach(() => {
  vi.stubGlobal(
    'PointerEvent',
    class extends MouseEvent {
      pointerId: number
      constructor(type: string, init: PointerEventInit = {}) {
        super(type, init)
        this.pointerId = init.pointerId ?? 1
      }
    },
  )
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    left: 0,
    width: 200,
    top: 0,
    right: 200,
    bottom: 88,
    height: 88,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  })
  HTMLElement.prototype.setPointerCapture = vi.fn()
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

it('continues dragging across replacement handles and commits the final owned fraction exactly once', () => {
  const commit = vi.fn()
  const view = render(<SegmentStrip segments={segments} onDragSetOverride={commit} />)
  const original = screen.getByRole('slider')
  fireEvent.pointerDown(original, { pointerId: 7 })
  fireEvent.pointerMove(original, { pointerId: 7, clientX: 120 })
  expect(original.isConnected).toBe(false)
  fireEvent.pointerMove(screen.getByRole('slider'), { pointerId: 7, clientX: 150 })
  fireEvent.pointerUp(document, { pointerId: 7 })
  expect(commit).toHaveBeenCalledExactlyOnceWith(0, 0.75)
  expect(view.container.querySelector('.seg-strip__segment')).toHaveStyle({ width: '75.000%' })
  fireEvent.pointerUp(document, { pointerId: 7 })
  expect(commit).toHaveBeenCalledTimes(1)
  expect(view.container.querySelector('img')).toBeNull()
})
it('ignores other pointers while an owned drag remains active', () => {
  const commit = vi.fn()
  render(<SegmentStrip segments={segments} onDragSetOverride={commit} />)
  const handle = screen.getByRole('slider')
  fireEvent.pointerDown(handle, { pointerId: 7 })
  fireEvent.pointerMove(document, { pointerId: 8, clientX: 180 })
  fireEvent.pointerUp(document, { pointerId: 8 })
  expect(commit).not.toHaveBeenCalled()
  fireEvent.pointerMove(document, { pointerId: 7, clientX: 130 })
  fireEvent.pointerUp(document, { pointerId: 7 })
  expect(commit).toHaveBeenCalledExactlyOnceWith(0, 0.65)
})
it('cancels without persisting partial widths and removes active listeners', () => {
  const commit = vi.fn()
  const view = render(<SegmentStrip segments={segments} onDragSetOverride={commit} />)
  fireEvent.pointerDown(screen.getByRole('slider'), { pointerId: 7 })
  fireEvent.pointerMove(document, { pointerId: 7, clientX: 150 })
  expect(view.container.querySelector('.seg-strip__segment')).toHaveStyle({ width: '75.000%' })
  fireEvent.pointerCancel(document, { pointerId: 7 })
  expect(view.container.querySelector('.seg-strip__segment')).toHaveStyle({ width: '50.000%' })
  fireEvent.pointerMove(document, { pointerId: 7, clientX: 180 })
  fireEvent.pointerUp(document, { pointerId: 7 })
  expect(commit).not.toHaveBeenCalled()
})
it.each(['unmount', 'replace'] as const)(
  'disposes an active drag on %s without mutating later state or committing',
  (action) => {
    const commit = vi.fn()
    const view = render(<SegmentStrip segments={segments} onDragSetOverride={commit} />)
    fireEvent.pointerDown(screen.getByRole('slider'), { pointerId: 7 })
    if (action === 'unmount') view.unmount()
    else
      view.rerender(
        <SegmentStrip
          segments={segments.map((seg) => ({ ...seg, fraction: 0.5 }))}
          onDragSetOverride={commit}
        />,
      )
    fireEvent.pointerMove(document, { pointerId: 7, clientX: 150 })
    fireEvent.pointerUp(document, { pointerId: 7 })
    expect(commit).not.toHaveBeenCalled()
    if (action === 'replace')
      expect(view.container.querySelector('.seg-strip__segment')).toHaveStyle({ width: '50.000%' })
  },
)
it('retains read-only strips without draggable handles', () => {
  render(<SegmentStrip segments={segments} isReadOnly onDragSetOverride={vi.fn()} />)
  expect(screen.queryByRole('slider')).not.toBeInTheDocument()
})

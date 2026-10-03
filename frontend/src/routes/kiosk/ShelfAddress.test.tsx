import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { Unit } from '../../api/types'
import { CubeContentsPanel } from './CubeContentsPanel'
import { ShelfGrid } from './ShelfGrid'

vi.mock('../../api/client', () => ({ fetchCubeContents: vi.fn() }))

const units: Unit[] = [
  { id: 42, display_name: 'Middle', rows: 3, cols: 2, ordering: 2 },
  { id: 7, display_name: 'Left', rows: 2, cols: 2, ordering: 1 },
  { id: 99, display_name: 'Right', rows: 2, cols: 2, ordering: 3 },
]
const cube = { unit_id: 99, row: 1, col: 1 }

function panel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  queryClient.setQueryData(['cube-contents', 99, 1, 1], {
    ...cube,
    first_label: 'LabelA',
    first_catalog: 'A 001',
    is_empty: false,
    total_count: 1,
    fill_level: 0.1,
    sample_records: [{ release_id: 1, label: 'LabelA', catalog_number: 'A 001' }],
  })
  return (
    <QueryClientProvider client={queryClient}>
      <CubeContentsPanel cube={cube} units={units} onDismiss={() => {}} />
    </QueryClientProvider>
  )
}

describe('ordered shelf cube addresses', () => {
  it('uses cumulative actual rows and the same address in the grid and tapped panel', () => {
    const onTap = vi.fn()
    const { container } = render(
      <>
        <ShelfGrid unit={units[2]} units={units} litCube={cube} onCubeTap={onTap} />
        {panel()}
      </>,
    )
    const lit = container.querySelector('[data-state="lit"]')!
    expect(lit).toHaveAttribute('aria-label', 'Cube G2')
    expect(container.querySelector('[role="dialog"]')).toHaveAttribute('aria-label', 'CUBE G2')
    fireEvent.click(lit)
    expect(onTap).toHaveBeenCalledWith(cube)
    expect(
      new Set(Array.from(container.querySelectorAll('.cube__address'), (cell) => cell.textContent))
        .size,
    ).toBe(4)
  })

  it('keeps coordinate identity and updates only display addressing when units reorder', () => {
    const { container, rerender } = render(
      <ShelfGrid unit={units[2]} units={units} litCube={cube} />,
    )
    const changed = units.map((unit) => (unit.id === 42 ? { ...unit, ordering: 4 } : unit))
    rerender(<ShelfGrid unit={units[2]} units={changed} litCube={cube} />)
    const lit = container.querySelector('[data-state="lit"]')!
    expect(lit).toHaveAttribute('aria-label', 'Cube D2')
    expect(lit).toHaveAttribute('data-unit-id', '99')
    expect(lit).toHaveAttribute('data-row', '1')
    expect(lit).toHaveAttribute('data-col', '1')
  })

  it('continues row letters past Z without unknown addresses or duplicate keys', () => {
    const tall: Unit = { id: 73, display_name: 'Tall', rows: 28, cols: 1, ordering: 1 }
    const { container } = render(
      <ShelfGrid unit={tall} units={[tall]} litCube={{ unit_id: 73, row: 26, col: 0 }} />,
    )
    expect(container.querySelector('[data-state="lit"]')).toHaveAttribute('aria-label', 'Cube AA1')
    expect(container.querySelector('[aria-label="Cube AB1"]')).not.toBeNull()
    expect(
      new Set(Array.from(container.querySelectorAll('.cube__address'), (cell) => cell.textContent))
        .size,
    ).toBe(28)
  })
})

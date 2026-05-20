/**
 * Tests for ShelfGrid cube-state matching (Bug 1 regression).
 *
 * The API returns 0-based row/col (e.g. primary_cube: {unit_id:1, row:0, col:0}).
 * ShelfGrid must match on the loop indices r/c directly — not on r+1/c+1.
 * Previously the code added +1 offsets, so row=0 never matched rowApi=1, and
 * no cube was ever lit.
 */
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Unit } from '../../api/types'
import { ShelfGrid } from './ShelfGrid'

const UNIT: Unit = { id: 1, display_name: 'Shelf A', rows: 4, cols: 4, ordering: 1 }

describe('ShelfGrid – 0-based cube lighting (Bug 1 fix)', () => {
  it('lights the top-left cube when litCube is {unit_id:1, row:0, col:0}', () => {
    const { container } = render(
      <ShelfGrid
        unit={UNIT}
        shelfIndex={0}
        litCube={{ unit_id: 1, row: 0, col: 0 }}
      />,
    )

    const litCells = container.querySelectorAll('[data-state="lit"]')
    expect(litCells).toHaveLength(1)

    const cell = litCells[0]
    expect(cell).toHaveAttribute('data-row', '0')
    expect(cell).toHaveAttribute('data-col', '0')
    expect(cell).toHaveAttribute('data-unit-id', '1')
    // Human-readable address for row=0, col=0 is "A1"
    expect(cell).toHaveAttribute('aria-label', 'Cube A1')
  })

  it('lights the bottom-right cube when litCube is {unit_id:1, row:3, col:3}', () => {
    const { container } = render(
      <ShelfGrid
        unit={UNIT}
        shelfIndex={0}
        litCube={{ unit_id: 1, row: 3, col: 3 }}
      />,
    )

    const litCells = container.querySelectorAll('[data-state="lit"]')
    expect(litCells).toHaveLength(1)

    const cell = litCells[0]
    expect(cell).toHaveAttribute('data-row', '3')
    expect(cell).toHaveAttribute('data-col', '3')
    // Human-readable address for row=3, col=3 is "D4"
    expect(cell).toHaveAttribute('aria-label', 'Cube D4')
  })

  it('lights no cubes when litCube is null', () => {
    const { container } = render(
      <ShelfGrid unit={UNIT} shelfIndex={0} litCube={null} />,
    )

    const litCells = container.querySelectorAll('[data-state="lit"]')
    expect(litCells).toHaveLength(0)
  })

  it('does not light any cube on a different unit_id', () => {
    const { container } = render(
      <ShelfGrid
        unit={UNIT}
        shelfIndex={0}
        litCube={{ unit_id: 2, row: 0, col: 0 }}
      />,
    )

    const litCells = container.querySelectorAll('[data-state="lit"]')
    expect(litCells).toHaveLength(0)
  })

  it('renders empty state for cubes in the emptyCubes set', () => {
    const emptyCubes = new Set(['1-2-3'])
    const { container } = render(
      <ShelfGrid
        unit={UNIT}
        shelfIndex={0}
        litCube={null}
        emptyCubes={emptyCubes}
      />,
    )

    const emptyCells = container.querySelectorAll('[data-state="empty"]')
    expect(emptyCells).toHaveLength(1)
    expect(emptyCells[0]).toHaveAttribute('data-row', '2')
    expect(emptyCells[0]).toHaveAttribute('data-col', '3')
  })

  it('lit state takes precedence over empty when the same cube is both lit and empty', () => {
    const emptyCubes = new Set(['1-0-0'])
    const { container } = render(
      <ShelfGrid
        unit={UNIT}
        shelfIndex={0}
        litCube={{ unit_id: 1, row: 0, col: 0 }}
        emptyCubes={emptyCubes}
      />,
    )

    // The cube at (0,0) must be lit, not empty
    const litCells = container.querySelectorAll('[data-state="lit"]')
    expect(litCells).toHaveLength(1)
    expect(litCells[0]).toHaveAttribute('data-row', '0')

    const emptyCells = container.querySelectorAll('[data-state="empty"]')
    expect(emptyCells).toHaveLength(0)
  })
})

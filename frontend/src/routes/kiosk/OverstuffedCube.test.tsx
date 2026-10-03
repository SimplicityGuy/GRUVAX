import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { Cube } from './Cube'
import { ShelfGrid } from './ShelfGrid'

afterEach(cleanup)
it.each([undefined, 0, 0.99, 1, 1.01, 3])(
  'applies the error ring only above capacity: %s',
  (fillLevel) => {
    render(
      <Cube
        unitId={7}
        row={1}
        col={2}
        state="lit"
        address="B3"
        fillLevel={fillLevel}
        subInterval={{
          start: 0.2,
          end: 0.4,
          next_cube: null,
          crosses_boundary: false,
        }}
        confidence={0.8}
      />,
    )
    const cube = screen.getByLabelText('Cube B3')
    expect(cube.classList.contains('is-overstuffed')).toBe(fillLevel != null && fillLevel > 1)
    expect(cube).toHaveAttribute('data-state', 'lit')
    expect(cube.querySelector('.sub-cube-bar')).not.toBeNull()
  },
)
it('maps bulk fill values to only their owned grid cells without changing empty or primary state', () => {
  render(
    <ShelfGrid
      unit={{ id: 73, display_name: 'Shelf', rows: 1, cols: 3, ordering: 1 }}
      litCube={{ unit_id: 73, row: 0, col: 1 }}
      emptyCubes={new Set(['73-0-2'])}
      fillLevels={
        new Map([
          ['73-0-0', 1],
          ['73-0-1', 1.01],
        ])
      }
    />,
  )
  expect(screen.getByLabelText('Cube A1')).not.toHaveClass('is-overstuffed')
  expect(screen.getByLabelText('Cube A2')).toHaveClass('is-overstuffed')
  expect(screen.getByLabelText('Cube A2')).toHaveAttribute('data-state', 'lit')
  expect(screen.getByLabelText('Cube A3')).not.toHaveClass('is-overstuffed')
  expect(screen.getByLabelText('Cube A3')).toHaveAttribute('data-state', 'empty')
})

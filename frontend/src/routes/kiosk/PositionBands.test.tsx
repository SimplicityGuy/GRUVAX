import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { SubInterval, Unit } from '../../api/types'
import { Cube } from './Cube'
import { ShelfGrid } from './ShelfGrid'

const primary = { unit_id: 1, row: 0, col: 0 }
const neighbor = { unit_id: 1, row: 0, col: 1 }
const unit: Unit = { id: 1, display_name: 'Shelf A', rows: 1, cols: 2, ordering: 1 }
const edgeBand: SubInterval = { start: 0.95, end: 1, crosses_boundary: true, next_cube: neighbor }

describe('record position bands', () => {
  it('renders the edge band only in the primary cube while retaining the label-span underlay', () => {
    const { container } = render(
      <ShelfGrid
        unit={unit}

        litCube={primary}
        labelSpan={[primary, neighbor]}
        subCubeInterval={edgeBand}
        confidence={0.8}
      />,
    )
    const primaryCell = container.querySelector('[aria-label="Cube A1"]')!
    const neighborCell = container.querySelector('[aria-label="Cube A2"]')!
    const band = primaryCell.querySelector<HTMLElement>('.sub-cube-bar')!
    expect(band.style.left).toBe('95%')
    expect(parseFloat(band.style.width)).toBeCloseTo(5)
    expect(band).not.toHaveClass('sub-cube-bar--singleton')
    expect(neighborCell).toHaveAttribute('data-state', 'dim')
    expect(neighborCell.querySelector('.sub-cube-bar')).toBeNull()
    expect(container.querySelectorAll('.span-underlay__band')).toHaveLength(1)
    expect(container.querySelectorAll('.sub-cube-bar')).toHaveLength(1)
  })
  it('renders a genuine singleton as a faint full-cube primary band', () => {
    const { container } = render(
      <ShelfGrid
        unit={unit}

        litCube={primary}
        labelSpan={[primary]}
        subCubeInterval={{ start: 0, end: 1, next_cube: null, crosses_boundary: false }}
        confidence={0.3}
      />,
    )
    const band = container.querySelector<HTMLElement>('.sub-cube-bar')!
    expect(band).toHaveClass('sub-cube-bar--singleton')
    expect(band.style.left).toBe('0%')
    expect(band.style.width).toBe('100%')
    expect(band.style.getPropertyValue('--confidence')).toBe('0.3')
    expect(band).toHaveAttribute('aria-label', 'approximate position')
    expect(container.querySelectorAll('.sub-cube-bar')).toHaveLength(1)
    expect(container.querySelector('.span-underlay__band')).toBeNull()
  })
  it('does not render a position band for a cube-only fallback', () => {
    const { container } = render(
      <ShelfGrid
        unit={unit}

        litCube={primary}
        labelSpan={[primary]}
        subCubeInterval={null}
        confidence={0.3}
      />,
    )
    expect(container.querySelector('[data-state="lit"]')).not.toBeNull()
    expect(container.querySelector('.sub-cube-bar')).toBeNull()
  })
  it('does not synthesize a position band in a dim Cube even with crossing metadata', () => {
    const { container } = render(
      <Cube
        unitId={1}
        row={0}
        col={1}
        address="A2"
        state="dim"
        subInterval={edgeBand}
        confidence={0.8}
      />,
    )
    expect(container.querySelector('.sub-cube-bar')).toBeNull()
  })
  it.each([0.125, 0.375, 0.625, 0.875])(
    'renders the exact shared-bin midpoint %s in the primary Cube',
    (position) => {
      const { container } = render(
        <Cube
          unitId={1}
          row={0}
          col={0}
          address="A1"
          state="lit"
          subInterval={{
            start: position - 0.05,
            end: position + 0.05,
            next_cube: null,
            crosses_boundary: false,
          }}
          confidence={0.4}
        />,
      )
      const band = container.querySelector<HTMLElement>('.sub-cube-bar')!
      expect(parseFloat(band.style.left)).toBeCloseTo((position - 0.05) * 100)
      expect(parseFloat(band.style.width)).toBeCloseTo(10)
      expect(band).not.toHaveClass('sub-cube-bar--singleton')
      expect(band).toHaveAttribute('aria-label', 'approximate position')
    },
  )
})

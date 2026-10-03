import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ShelfGrid } from './ShelfGrid'

// The band is a sibling of the grid inside that unit's relative wrapper.
describe('per-unit span geometry', () => {
  it.each([2, 73])('keeps unit %s and later rows in local coordinates', (id) => {
    const unit = { id, display_name: 'Later shelf', rows: 4, cols: 4, ordering: 3 }
    const { container } = render(
      <ShelfGrid
        unit={unit}
        litCube={null}
        labelSpan={[
          { unit_id: id, row: 2, col: 1 },
          { unit_id: id, row: 2, col: 3 },
        ]}
      />,
    )
    const band = container.querySelector<HTMLElement>('.span-underlay__band')!
    expect(band.style.left).toBe('92px')
    expect(band.style.width).toBe('264px')
    expect(band.style.top).toBe('238px')
    expect(parseFloat(band.style.left) + parseFloat(band.style.width)).toBe(356)
  })
  it('produces separate row bands without a shelf-area offset for a wrapping span', () => {
    const unit = { id: 42, display_name: 'Wrap', rows: 4, cols: 4, ordering: 2 }
    const { container } = render(
      <ShelfGrid
        unit={unit}
        litCube={null}
        labelSpan={[
          { unit_id: 42, row: 1, col: 3 },
          { unit_id: 42, row: 2, col: 0 },
        ]}
      />,
    )
    const bands = Array.from(container.querySelectorAll<HTMLElement>('.span-underlay__band'))
    expect(bands.map((band) => [band.style.left, band.style.top, band.style.width])).toEqual([
      ['276px', '146px', '80px'],
      ['0px', '238px', '80px'],
    ])
  })
})

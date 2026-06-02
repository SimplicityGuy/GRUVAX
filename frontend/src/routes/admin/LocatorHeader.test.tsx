/**
 * Tests for LocatorHeader fill shading, empty state, lit priority, clamp, and popover.
 *
 * Uses data-row / data-col attributes (added in Task 3 implementation) to
 * target cells deterministically. Asserts the --fill custom property directly
 * via toHaveStyle — jsdom cannot evaluate color-mix(), so we test the property
 * that drives it rather than the computed background color.
 *
 * No QueryClient wrapper needed — LocatorHeader is display-only and takes
 * cubes via prop with no data fetching.
 */
import { fireEvent, render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { AdminCube } from '../../api/types'
import { LocatorHeader } from './LocatorHeader'

/** Factory for AdminCube test fixtures. */
function makeCube(row: number, col: number, overrides?: Partial<AdminCube>): AdminCube {
  return {
    unit_id: 1,
    row,
    col,
    first_label: 'Test Label',
    first_catalog: 'T-001',
    is_empty: false,
    fill_level: 0.5,
    record_count: 25,
    ...overrides,
  }
}

describe('LocatorHeader fill shading', () => {
  it('renders .locator-cell--fill with --fill style for a non-empty cube (fill_level 0.75)', () => {
    const cubes = [makeCube(0, 0, { fill_level: 0.75 })]
    const { container } = render(
      <LocatorHeader unitId={1} row={-1} col={-1} cubes={cubes} />,
    )
    const cell = container.querySelector('[data-row="0"][data-col="0"]')
    expect(cell).toHaveClass('locator-cell--fill')
    expect(cell).toHaveStyle('--fill: 0.75')
  })

  it('renders .locator-cell--empty and NOT .locator-cell--fill for an empty cube', () => {
    const cubes = [makeCube(0, 0, { is_empty: true, fill_level: 0 })]
    const { container } = render(
      <LocatorHeader unitId={1} row={-1} col={-1} cubes={cubes} />,
    )
    const cell = container.querySelector('[data-row="0"][data-col="0"]')
    expect(cell).toHaveClass('locator-cell--empty')
    expect(cell).not.toHaveClass('locator-cell--fill')
  })

  it('renders .locator-cell--lit (not --fill) when the edited bin matches row/col', () => {
    const cubes = [makeCube(2, 1, { fill_level: 0.9 })]
    const { container } = render(
      <LocatorHeader unitId={1} row={2} col={1} cubes={cubes} />,
    )
    const cell = container.querySelector('[data-row="2"][data-col="1"]')
    expect(cell).toHaveClass('locator-cell--lit')
    expect(cell).not.toHaveClass('locator-cell--fill')
  })

  it('clamps fill_level > 1.0 to 1 for the --fill custom property (D-03)', () => {
    const cubes = [makeCube(0, 0, { fill_level: 1.5 })]
    const { container } = render(
      <LocatorHeader unitId={1} row={-1} col={-1} cubes={cubes} />,
    )
    const cell = container.querySelector('[data-row="0"][data-col="0"]')
    expect(cell).toHaveStyle('--fill: 1')
  })
})

describe('LocatorHeader popover (D-05 / D-06)', () => {
  it('tapping a filled cell reveals a .locator-fill-popover with bin ID and record count', () => {
    const cubes = [makeCube(0, 0, { fill_level: 0.5, record_count: 50 })]
    const { container } = render(
      <LocatorHeader unitId={1} row={-1} col={-1} cubes={cubes} />,
    )
    const cell = container.querySelector('[data-row="0"][data-col="0"]')!
    fireEvent.click(cell)
    const popover = container.querySelector('.locator-fill-popover')
    expect(popover).not.toBeNull()
    // bin ID: unitId=1 → letter "A", row=0, col=0 → bin 1 → "A1"
    expect(popover?.textContent).toContain('A1')
    expect(popover?.textContent).toContain('50')
  })

  it('tapping the same cell again dismisses the popover', () => {
    const cubes = [makeCube(0, 0, { fill_level: 0.5 })]
    const { container } = render(
      <LocatorHeader unitId={1} row={-1} col={-1} cubes={cubes} />,
    )
    const cell = container.querySelector('[data-row="0"][data-col="0"]')!
    fireEvent.click(cell)
    expect(container.querySelector('.locator-fill-popover')).not.toBeNull()
    fireEvent.click(cell)
    expect(container.querySelector('.locator-fill-popover')).toBeNull()
  })

  it('pressing Escape dismisses an open popover', () => {
    const cubes = [makeCube(0, 0, { fill_level: 0.5 })]
    const { container } = render(
      <LocatorHeader unitId={1} row={-1} col={-1} cubes={cubes} />,
    )
    const cell = container.querySelector('[data-row="0"][data-col="0"]')!
    fireEvent.click(cell)
    expect(container.querySelector('.locator-fill-popover')).not.toBeNull()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(container.querySelector('.locator-fill-popover')).toBeNull()
  })

  it('tapping an empty cube popover shows bin ID and "Empty bin" text', () => {
    const cubes = [makeCube(0, 0, { is_empty: true, fill_level: 0, record_count: 0 })]
    const { container } = render(
      <LocatorHeader unitId={1} row={-1} col={-1} cubes={cubes} />,
    )
    const cell = container.querySelector('[data-row="0"][data-col="0"]')!
    fireEvent.click(cell)
    const popover = container.querySelector('.locator-fill-popover')
    expect(popover).not.toBeNull()
    expect(popover?.textContent).toContain('A1')
    expect(popover?.textContent).toContain('Empty bin')
  })
})

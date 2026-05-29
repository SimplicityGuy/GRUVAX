/**
 * Tests for the ShelfLayoutNotConfigured affordance (Phase 2 / Plan 09).
 *
 * Covers:
 *   Test 1 (store): shelfLayoutUnavailable flag transitions
 *     - setLocateResult with null primary_cube + confidence 0 → true
 *     - setLocateResult with a real cube + confidence > 0 → false
 *     - clearSearch resets it to false
 *
 *   Test 2 (component render): ShelfLayoutNotConfigured renders Nordic-Grid copy
 *     - heading text present
 *     - body text present
 *     - root element carries the expected className
 *     - no hardcoded hex in inline styles (relies on CSS classes/tokens)
 */
import { beforeEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { useGruvaxStore } from '../../state/store'
import { ShelfLayoutNotConfigured } from './ShelfLayoutNotConfigured'

// ── Store reset helper (mirrors store.connectivity.test.ts pattern) ──────────

function resetStore() {
  useGruvaxStore.setState({
    query: '',
    selectedReleaseId: null,
    selectedResult: null,
    highlight: { primaryCube: null },
    labelSpan: [],
    subCubeInterval: null,
    confidence: 0,
    animationToken: 0,
    shelfLayoutUnavailable: false,
    connectivity: { sseConnected: false, lastSeenAt: 0, bannerVisible: false },
    shimmerCubes: [],
    shimmerExpiresAt: 0,
  })
}

// ── Test 1: shelfLayoutUnavailable store slice ────────────────────────────────

describe('store – shelfLayoutUnavailable flag (Plan 09 / D-12)', () => {
  beforeEach(() => {
    resetStore()
  })

  it('setLocateResult with null primary_cube and confidence 0 sets shelfLayoutUnavailable true', () => {
    useGruvaxStore.getState().setLocateResult({
      release_id: 42,
      primary_cube: null,
      label_span: [],
      sub_cube_interval: null,
      confidence: 0,
      generated_at: '2026-01-01T00:00:00Z',
      estimator_version: '1',
    })
    expect(useGruvaxStore.getState().shelfLayoutUnavailable).toBe(true)
  })

  it('setLocateResult with a real primary_cube and confidence > 0 sets shelfLayoutUnavailable false', () => {
    // First set to true so we confirm it resets
    useGruvaxStore.setState({ shelfLayoutUnavailable: true })

    useGruvaxStore.getState().setLocateResult({
      release_id: 1351,
      primary_cube: { unit_id: 1, row: 2, col: 3 },
      label_span: [{ unit_id: 1, row: 2, col: 3 }],
      sub_cube_interval: { start: 0.2, end: 0.5, crosses_boundary: false },
      confidence: 0.85,
      generated_at: '2026-01-01T00:00:00Z',
      estimator_version: '1',
    })
    expect(useGruvaxStore.getState().shelfLayoutUnavailable).toBe(false)
  })

  it('setLocateResult with a real primary_cube but confidence 0 sets shelfLayoutUnavailable false', () => {
    // primary_cube present means we have a cube, even if confidence is 0
    useGruvaxStore.getState().setLocateResult({
      release_id: 99,
      primary_cube: { unit_id: 2, row: 0, col: 0 },
      label_span: [],
      sub_cube_interval: null,
      confidence: 0,
      generated_at: '2026-01-01T00:00:00Z',
      estimator_version: '1',
    })
    // Only null primary_cube + 0 confidence triggers the flag
    expect(useGruvaxStore.getState().shelfLayoutUnavailable).toBe(false)
  })

  it('clearSearch resets shelfLayoutUnavailable to false', () => {
    // Set flag via a locate result
    useGruvaxStore.getState().setLocateResult({
      release_id: 42,
      primary_cube: null,
      label_span: [],
      sub_cube_interval: null,
      confidence: 0,
      generated_at: '2026-01-01T00:00:00Z',
      estimator_version: '1',
    })
    expect(useGruvaxStore.getState().shelfLayoutUnavailable).toBe(true)

    // clearSearch must reset it
    useGruvaxStore.getState().clearSearch()
    expect(useGruvaxStore.getState().shelfLayoutUnavailable).toBe(false)
  })
})

// ── Test 2: ShelfLayoutNotConfigured component render ─────────────────────────

describe('ShelfLayoutNotConfigured', () => {
  it('renders the heading plain-language copy (sentence case)', () => {
    render(<ShelfLayoutNotConfigured />)
    expect(screen.getByText('Shelf layout not set up yet')).toBeDefined()
  })

  it('renders the body plain-language copy', () => {
    render(<ShelfLayoutNotConfigured />)
    const body = screen.getByText(
      /This collection.s records are loaded/i,
    )
    expect(body).toBeDefined()
  })

  it('root element carries the shelf-layout-unconfigured class', () => {
    const { container } = render(<ShelfLayoutNotConfigured />)
    const root = container.firstChild as HTMLElement
    expect(root.classList.contains('shelf-layout-unconfigured')).toBe(true)
  })

  it('heading element carries the shelf-layout-unconfigured__heading class', () => {
    render(<ShelfLayoutNotConfigured />)
    const heading = screen.getByText('Shelf layout not set up yet')
    expect(heading.classList.contains('shelf-layout-unconfigured__heading')).toBe(true)
  })

  it('body element carries the shelf-layout-unconfigured__body class', () => {
    render(<ShelfLayoutNotConfigured />)
    const body = screen.getByText(/This collection.s records are loaded/i)
    expect(body.classList.contains('shelf-layout-unconfigured__body')).toBe(true)
  })

  it('does not render any inline hex color styles (tokens only — no hardcoded hex)', () => {
    const { container } = render(<ShelfLayoutNotConfigured />)
    // Walk all DOM elements and check that their style attribute contains no hex colors
    const allElements = Array.from(container.querySelectorAll('*'))
    for (const el of allElements) {
      const inlineStyle = el.getAttribute('style') ?? ''
      // Hex color pattern: #RGB or #RRGGBB
      expect(inlineStyle).not.toMatch(/#[0-9a-fA-F]{3,6}/)
    }
  })
})

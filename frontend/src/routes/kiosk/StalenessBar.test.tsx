/**
 * StalenessBar component tests — OBS-06, D-01/D-02.
 *
 * Covers the threshold-gated render logic:
 *   - null: hidden (health unavailable → offline banner leads)
 *   - < 14d: hidden (not stale)
 *   - > 14d: banner with exact Nordic Grid copy + a11y attrs
 *
 * D-02 guard: no staleness hint in the no-results path (NoResultsRow is
 * separately static; this test confirms StalenessBar itself does not
 * reference any no-results staleness copy).
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StalenessBar } from './StalenessBar'

const STALE_THRESHOLD = 14 * 24 * 60 * 60  // 1_209_600s — D-01

describe('StalenessBar', () => {
  describe('hidden states', () => {
    it('renders nothing when syncAgeSeconds is null', () => {
      const { container } = render(<StalenessBar syncAgeSeconds={null} />)
      expect(container.firstChild).toBeNull()
    })

    it('renders nothing when syncAgeSeconds is 0', () => {
      const { container } = render(<StalenessBar syncAgeSeconds={0} />)
      expect(container.firstChild).toBeNull()
    })

    it('renders nothing when syncAgeSeconds is exactly below threshold (< 14d)', () => {
      // One second below 14 days
      const { container } = render(<StalenessBar syncAgeSeconds={STALE_THRESHOLD - 1} />)
      expect(container.firstChild).toBeNull()
    })

    it('renders nothing when syncAgeSeconds equals the threshold exactly (not strictly greater)', () => {
      const { container } = render(<StalenessBar syncAgeSeconds={STALE_THRESHOLD} />)
      expect(container.firstChild).toBeNull()
    })

    it('renders nothing for a recent sync (100 seconds)', () => {
      const { container } = render(<StalenessBar syncAgeSeconds={100} />)
      expect(container.firstChild).toBeNull()
    })
  })

  describe('visible state (> 14 days)', () => {
    it('renders the banner when syncAgeSeconds is 1_209_601 (one second over 14d)', () => {
      render(<StalenessBar syncAgeSeconds={1_209_601} />)
      expect(screen.getByRole('alert')).toBeDefined()
    })

    it('contains the exact copy "Collection data may be outdated" (UI-SPEC §Banner copy)', () => {
      render(<StalenessBar syncAgeSeconds={1_209_601} />)
      const banner = screen.getByRole('alert')
      expect(banner.textContent).toContain('Collection data may be outdated')
    })

    it('contains the em dash separator in copy (UI-SPEC §Banner copy)', () => {
      render(<StalenessBar syncAgeSeconds={1_209_601} />)
      const banner = screen.getByRole('alert')
      // em dash is U+2014 (—)
      expect(banner.textContent).toContain('—')
    })

    it('shows whole days — 14d for 1_209_601s (Math.floor, no hours suffix)', () => {
      // 1_209_601 / 86400 = 14.00001... → Math.floor = 14
      render(<StalenessBar syncAgeSeconds={1_209_601} />)
      const banner = screen.getByRole('alert')
      expect(banner.textContent).toContain('14d')
    })

    it('shows correct whole days for a larger age (18d)', () => {
      // 18 days in seconds = 1_555_200
      render(<StalenessBar syncAgeSeconds={18 * 86400} />)
      const banner = screen.getByRole('alert')
      expect(banner.textContent).toContain('18d')
    })

    it('shows correct whole days for 30d', () => {
      render(<StalenessBar syncAgeSeconds={30 * 86400} />)
      const banner = screen.getByRole('alert')
      expect(banner.textContent).toContain('30d')
    })

    it('uses Math.floor — partial extra day does not bump the count', () => {
      // 18 days + 23 hours → still 18d displayed
      const age = 18 * 86400 + 23 * 3600
      render(<StalenessBar syncAgeSeconds={age} />)
      const banner = screen.getByRole('alert')
      expect(banner.textContent).toContain('18d')
      expect(banner.textContent).not.toContain('19d')
    })

    it('has aria-live="polite" on the banner element (a11y — no re-announce on every render)', () => {
      render(<StalenessBar syncAgeSeconds={1_209_601} />)
      const banner = screen.getByRole('alert')
      expect(banner.getAttribute('aria-live')).toBe('polite')
    })

    it('contains an aria-hidden warning SVG icon (decorative, not load-bearing)', () => {
      render(<StalenessBar syncAgeSeconds={1_209_601} />)
      const banner = screen.getByRole('alert')
      const svg = banner.querySelector('svg')
      expect(svg).not.toBeNull()
      expect(svg?.getAttribute('aria-hidden')).toBe('true')
    })

    it('has the staleness-bar class for CSS token wiring', () => {
      render(<StalenessBar syncAgeSeconds={1_209_601} />)
      const banner = screen.getByRole('alert')
      expect(banner.classList.contains('staleness-bar')).toBe(true)
    })

    it('does not include "ago" count as hours (no "h" suffix in kiosk banner)', () => {
      render(<StalenessBar syncAgeSeconds={1_209_601} />)
      const banner = screen.getByRole('alert')
      // Should contain "14d ago" not "14h" or similar
      expect(banner.textContent).toContain('14d ago')
      expect(banner.textContent).not.toMatch(/\d+h/)
    })

    it('does not contain technical jargon (no "sync_age_seconds", "collection_items")', () => {
      render(<StalenessBar syncAgeSeconds={1_209_601} />)
      const banner = screen.getByRole('alert')
      expect(banner.textContent).not.toContain('sync_age_seconds')
      expect(banner.textContent).not.toContain('collection_items')
      expect(banner.textContent).not.toContain('SYNC STALE')
    })
  })
})

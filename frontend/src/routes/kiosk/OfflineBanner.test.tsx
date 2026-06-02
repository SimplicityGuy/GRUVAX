/**
 * OfflineBanner component tests — OFF-01, D-01..D-04.
 *
 * Covers SSE-authoritative offline render logic:
 *   - sseConnected=true → renders nothing (early return)
 *   - sseConnected=false, navigator.onLine=true → "Can't reach GRUVAX" copy + role="alert"
 *   - sseConnected=false, navigator.onLine=false → "No network" copy + role="alert"
 *
 * PITFALLS 35: SSE state is the authoritative signal; navigator.onLine is only cosmetic hint.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { OfflineBanner } from './OfflineBanner'
import { useGruvaxStore } from '../../state/store'

// Helper: mock navigator.onLine via Object.defineProperty
function mockNavigatorOnLine(value: boolean) {
  Object.defineProperty(navigator, 'onLine', {
    writable: true,
    configurable: true,
    value,
  })
}

describe('OfflineBanner', () => {
  beforeEach(() => {
    // Reset store to connected state (banner should be hidden by default)
    useGruvaxStore.setState({
      connectivity: { sseConnected: true, lastSeenAt: Date.now(), bannerVisible: false },
    })
    // Default: online
    mockNavigatorOnLine(true)
  })

  afterEach(() => {
    // Restore default state
    mockNavigatorOnLine(true)
    useGruvaxStore.setState({
      connectivity: { sseConnected: true, lastSeenAt: Date.now(), bannerVisible: false },
    })
  })

  describe('connected state', () => {
    it('renders nothing when sseConnected is true (early return)', () => {
      useGruvaxStore.setState({
        connectivity: { sseConnected: true, lastSeenAt: Date.now(), bannerVisible: false },
      })
      const { container } = render(<OfflineBanner />)
      expect(container.firstChild).toBeNull()
    })

    it('queryByRole("alert") is null when sseConnected is true', () => {
      useGruvaxStore.setState({
        connectivity: { sseConnected: true, lastSeenAt: Date.now(), bannerVisible: false },
      })
      render(<OfflineBanner />)
      expect(screen.queryByRole('alert')).toBeNull()
    })
  })

  describe('disconnected state — navigator.onLine=true (server unreachable)', () => {
    beforeEach(() => {
      useGruvaxStore.setState({
        connectivity: { sseConnected: false, lastSeenAt: 0, bannerVisible: true },
      })
      mockNavigatorOnLine(true)
    })

    it('shows role="alert" when sseConnected is false', () => {
      render(<OfflineBanner />)
      expect(screen.getByRole('alert')).toBeDefined()
    })

    it('shows "Can\'t reach GRUVAX — trying to reconnect…" when onLine=true', () => {
      render(<OfflineBanner />)
      const banner = screen.getByRole('alert')
      expect(banner.textContent).toContain("Can't reach GRUVAX — trying to reconnect…")
    })

    it('has aria-live="polite" for accessibility', () => {
      render(<OfflineBanner />)
      const banner = screen.getByRole('alert')
      expect(banner.getAttribute('aria-live')).toBe('polite')
    })

    it('has the offline-banner CSS class for token wiring', () => {
      render(<OfflineBanner />)
      const banner = screen.getByRole('alert')
      expect(banner.classList.contains('offline-banner')).toBe(true)
    })

    it('contains an aria-hidden SVG icon (decorative connectivity indicator)', () => {
      render(<OfflineBanner />)
      const banner = screen.getByRole('alert')
      const svg = banner.querySelector('svg')
      expect(svg).not.toBeNull()
      expect(svg?.getAttribute('aria-hidden')).toBe('true')
    })

    it('does NOT show a close/dismiss button (D-04 — not dismissible)', () => {
      render(<OfflineBanner />)
      const banner = screen.getByRole('alert')
      const buttons = banner.querySelectorAll('button')
      expect(buttons.length).toBe(0)
    })
  })

  describe('disconnected state — navigator.onLine=false (no network)', () => {
    beforeEach(() => {
      useGruvaxStore.setState({
        connectivity: { sseConnected: false, lastSeenAt: 0, bannerVisible: true },
      })
      mockNavigatorOnLine(false)
    })

    it('shows role="alert" when both sseConnected=false and onLine=false', () => {
      render(<OfflineBanner />)
      expect(screen.getByRole('alert')).toBeDefined()
    })

    it('shows "No network — trying to reconnect…" when onLine=false', () => {
      render(<OfflineBanner />)
      const banner = screen.getByRole('alert')
      expect(banner.textContent).toContain('No network — trying to reconnect…')
    })

    it('does NOT show the "Can\'t reach GRUVAX" variant when onLine=false', () => {
      render(<OfflineBanner />)
      const banner = screen.getByRole('alert')
      expect(banner.textContent).not.toContain("Can't reach GRUVAX")
    })
  })
})

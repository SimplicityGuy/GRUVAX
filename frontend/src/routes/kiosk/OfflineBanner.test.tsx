/**
 * OfflineBanner component tests — OFF-01, D-01..D-04, gap-closure 09-05.
 *
 * Covers SSE-authoritative offline render logic:
 *   - bannerVisible=false (never-connected: sseConnected=false, everConnected=false) → renders nothing
 *   - bannerVisible=false (connected: sseConnected=true, everConnected=true) → renders nothing
 *   - bannerVisible=true (offline-confirmed), navigator.onLine=true → "Can't reach GRUVAX" copy + role="alert"
 *   - bannerVisible=true (offline-confirmed), navigator.onLine=false → "No network" copy + role="alert"
 *
 * PITFALLS 35: SSE state is the authoritative signal; navigator.onLine is only cosmetic hint.
 * gap-closure 09-05: bannerVisible = !sseConnected AND everConnected — never just !sseConnected.
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
      connectivity: { sseConnected: true, lastSeenAt: Date.now(), everConnected: true, bannerVisible: false },
    })
    // Default: online
    mockNavigatorOnLine(true)
  })

  afterEach(() => {
    // Restore default state
    mockNavigatorOnLine(true)
    useGruvaxStore.setState({
      connectivity: { sseConnected: true, lastSeenAt: Date.now(), everConnected: true, bannerVisible: false },
    })
  })

  describe('never-connected state (gap-closure 09-05)', () => {
    it('renders nothing when never connected (sseConnected=false, everConnected=false, bannerVisible=false)', () => {
      // Simulates initial bootstrap / 403 device_unknown — first SSE connection never opened
      useGruvaxStore.setState({
        connectivity: { sseConnected: false, lastSeenAt: 0, everConnected: false, bannerVisible: false },
      })
      const { container } = render(<OfflineBanner />)
      expect(container.firstChild).toBeNull()
    })

    it('queryByRole("alert") is null when never connected', () => {
      useGruvaxStore.setState({
        connectivity: { sseConnected: false, lastSeenAt: 0, everConnected: false, bannerVisible: false },
      })
      render(<OfflineBanner />)
      expect(screen.queryByRole('alert')).toBeNull()
    })
  })

  describe('connected state', () => {
    it('renders nothing when bannerVisible is false (sseConnected=true)', () => {
      useGruvaxStore.setState({
        connectivity: { sseConnected: true, lastSeenAt: Date.now(), everConnected: true, bannerVisible: false },
      })
      const { container } = render(<OfflineBanner />)
      expect(container.firstChild).toBeNull()
    })

    it('queryByRole("alert") is null when bannerVisible is false', () => {
      useGruvaxStore.setState({
        connectivity: { sseConnected: true, lastSeenAt: Date.now(), everConnected: true, bannerVisible: false },
      })
      render(<OfflineBanner />)
      expect(screen.queryByRole('alert')).toBeNull()
    })
  })

  describe('offline-confirmed state — navigator.onLine=true (server unreachable)', () => {
    beforeEach(() => {
      // offline-confirmed: was connected, then lost (gap-closure 09-05)
      useGruvaxStore.setState({
        connectivity: { sseConnected: false, lastSeenAt: 0, everConnected: true, bannerVisible: true },
      })
      mockNavigatorOnLine(true)
    })

    it('shows role="alert" when offline-confirmed (bannerVisible=true)', () => {
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

  describe('offline-confirmed state — navigator.onLine=false (no network)', () => {
    beforeEach(() => {
      // offline-confirmed: was connected, then lost (gap-closure 09-05)
      useGruvaxStore.setState({
        connectivity: { sseConnected: false, lastSeenAt: 0, everConnected: true, bannerVisible: true },
      })
      mockNavigatorOnLine(false)
    })

    it('shows role="alert" when offline-confirmed (bannerVisible=true) and onLine=false', () => {
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

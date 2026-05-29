/**
 * PairView RED tests — DEV-03 /pair countdown + auto-reroll (Wave 0 scaffold).
 *
 * Tests:
 *   1. Countdown renders in M:SS format (e.g. "4:59") after pairing-code fetch
 *   2. On expiry (0:00), PairView auto-rerolls by issuing a SECOND POST to
 *      /api/devices/pairing-codes
 *
 * Both tests are RED against the PairView stub (returns null / placeholder div).
 * Plan 03-04 implements the real PairView; these tests go GREEN at that point.
 *
 * Fake timers strategy (mirrors StalenessBar.test.tsx + ProfileDrawer.test.tsx):
 *   - vi.useFakeTimers() in beforeEach
 *   - vi.advanceTimersByTimeAsync to drive the countdown
 *   - vi.useRealTimers() in afterEach
 *
 * Fetch mock: replaces global.fetch with a vi.fn() that returns a pairing-code
 * response for POST /api/devices/pairing-codes and an unpaired device state for
 * GET /api/devices/me.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'

import { PairView } from './PairView'

// ── Helpers ──────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 0,
        gcTime: 0,
      },
    },
  })
}

// Pairing code fixture: expires in ~5 minutes from "now" (fake timer epoch).
// Using a relative value so the countdown test reads 4:59 on first render.
const FAKE_NOW_MS = 1_000_000_000_000 // arbitrary frozen "now"
const EXPIRES_AT_ISO = new Date(FAKE_NOW_MS + 5 * 60 * 1000 - 1000).toISOString() // ~4:59 remaining

function makeFetch(callCount: { value: number }) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method?.toUpperCase() ?? 'GET'
    if (typeof url === 'string' && url.includes('/api/devices/pairing-codes') && method === 'POST') {
      callCount.value += 1
      return {
        ok: true,
        json: async () => ({ code: '1234', expires_at: EXPIRES_AT_ISO }),
      } as Response
    }
    if (typeof url === 'string' && url.includes('/api/devices/me')) {
      return {
        ok: true,
        json: async () => ({ state: 'unpaired', profile_id: null }),
      } as Response
    }
    return { ok: false, json: async () => ({}) } as Response
  })
}

// ── Setup / Teardown ─────────────────────────────────────────────────────────

beforeEach(() => {
  // Freeze time at FAKE_NOW_MS so the countdown starting point is deterministic.
  vi.useFakeTimers({ now: FAKE_NOW_MS, shouldAdvanceTime: false })
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('PairView', () => {
  /**
   * Test 1: countdown renders in M:SS format.
   *
   * After mounting PairView:
   *   - Component fetches POST /api/devices/pairing-codes
   *   - Gets back {code:'1234', expires_at: ~4:59 from now}
   *   - Renders the countdown in M:SS format (e.g. "4:59")
   *
   * RED against the stub (no countdown rendered — stub returns <div data-testid="pair-view" />).
   * GREEN when Plan 03-04 implements the countdown display.
   */
  it('renders countdown in M:SS format after pairing code fetch', async () => {
    const callCount = { value: 0 }
    vi.stubGlobal('fetch', makeFetch(callCount))

    const qc = makeQueryClient()
    await act(async () => {
      render(
        <QueryClientProvider client={qc}>
          <MemoryRouter>
            <PairView />
          </MemoryRouter>
        </QueryClientProvider>,
      )
      // Flush promises so the fetch resolves and the component updates
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })

    // The countdown should be visible in M:SS format.
    // Exact value depends on timing; we assert the pattern M:SS (e.g. "4:59").
    // The regex matches any "digit:digit-digit" pattern (M:SS).
    const container = document.body
    const hasCountdown = /\d:\d\d/.test(container.textContent ?? '')
    expect(hasCountdown).toBe(true)
  })

  /**
   * Test 2: auto-reroll on expiry.
   *
   * After the countdown reaches 0:00, PairView must automatically fetch a NEW
   * pairing code (second POST to /api/devices/pairing-codes).
   *
   * RED against the stub (no countdown logic → fetch never fires twice).
   * GREEN when Plan 03-04 implements the auto-reroll on expiry.
   */
  it('auto-rerolls the pairing code when countdown reaches 0:00', async () => {
    const callCount = { value: 0 }
    vi.stubGlobal('fetch', makeFetch(callCount))

    const qc = makeQueryClient()
    await act(async () => {
      render(
        <QueryClientProvider client={qc}>
          <MemoryRouter>
            <PairView />
          </MemoryRouter>
        </QueryClientProvider>,
      )
      await Promise.resolve()
      await Promise.resolve()
    })

    // Advance fake timers past the expiry (5 minutes + 2 seconds buffer)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5 * 60 * 1000 + 2000)
    })

    // After expiry, PairView must have fired a second POST /api/devices/pairing-codes.
    // callCount.value should be >= 2 (initial fetch + auto-reroll).
    expect(callCount.value).toBeGreaterThanOrEqual(2)
  })
})

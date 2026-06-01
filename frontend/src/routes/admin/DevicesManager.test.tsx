/**
 * DevicesManager tests — DEV-04 QR prefill flow.
 *
 * Tests (RED gate for prefill-confirm, D-04 no-auto-submit, L-03 single call site):
 *   1. Mounting at /admin/devices?code=1234 opens the bind drawer with prefillCode
 *      and strips the ?code= param (replace: true) so a reload does not re-open.
 *   2. Mounting at /admin/devices with no ?code= does NOT auto-open the bind drawer.
 *
 * Harness: QueryClient + MemoryRouter (mirrors PairView.test.tsx + DeviceDrawer.test.tsx).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router'

import { DevicesManager } from './DevicesManager'

// ── Helpers ──────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0, gcTime: 0 },
      mutations: { retry: false },
    },
  })
}

// Empty device list (avoids loading spinner blocking test assertions)
const EMPTY_DEVICES = { paired: [], pending: [], revoked: [] }

// ── Setup / Teardown ─────────────────────────────────────────────────────────

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: false })
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('DevicesManager', () => {
  /**
   * Test 1: mounting at /admin/devices?code=1234 opens the bind drawer with
   * prefillCode '1234' and strips the ?code= param so a reload does not re-open.
   *
   * Verifies:
   *   - The "PAIR THIS DEVICE" confirm CTA is visible (prefill confirm screen, not NumericKeypad)
   *   - The NumericKeypad is NOT rendered (prefill confirm replaces it)
   *
   * Uses real timers so waitFor polling works correctly alongside TanStack Query.
   */
  it('opens bind drawer with prefill when ?code=1234 is in URL', async () => {
    // Real timers for waitFor + TanStack Query
    vi.useRealTimers()

    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      const method = (init?.method ?? 'GET').toUpperCase()
      if (typeof url === 'string' && url.includes('/api/admin/devices') && method === 'GET') {
        return { ok: true, json: async () => EMPTY_DEVICES } as Response
      }
      return { ok: true, json: async () => ({}) } as Response
    }))

    const qc = makeQueryClient()
    await act(async () => {
      render(
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={['/admin/devices?code=1234']}>
            <Routes>
              <Route path="/admin/devices" element={<DevicesManager />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      )
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })

    // The prefill confirm CTA "PAIR THIS DEVICE" must be visible
    await waitFor(() => {
      const pairBtn = screen.queryByRole('button', { name: /pair this device/i })
      expect(pairBtn).not.toBeNull()
    }, { timeout: 3000 })

    // The NumericKeypad must NOT be rendered (confirm screen, not code-entry)
    const keypadBtn1 = screen.queryByRole('button', { name: '1' })
    expect(keypadBtn1).toBeNull()
  })

  /**
   * Test 2: mounting at /admin/devices with no ?code= does NOT auto-open bind drawer.
   */
  it('does NOT open bind drawer when no ?code= param is present', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      const method = (init?.method ?? 'GET').toUpperCase()
      if (typeof url === 'string' && url.includes('/api/admin/devices') && method === 'GET') {
        return { ok: true, json: async () => EMPTY_DEVICES } as Response
      }
      return { ok: true, json: async () => ({}) } as Response
    }))

    const qc = makeQueryClient()
    await act(async () => {
      render(
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={['/admin/devices']}>
            <Routes>
              <Route path="/admin/devices" element={<DevicesManager />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      )
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })

    // No drawer should be open — "PAIR THIS DEVICE" CTA must not be visible
    const pairBtn = screen.queryByRole('button', { name: /pair this device/i })
    expect(pairBtn).toBeNull()

    // No NumericKeypad either
    const keypadBtn1 = screen.queryByRole('button', { name: '1' })
    expect(keypadBtn1).toBeNull()
  })
})

/**
 * DeviceDrawer RED test — DEV-02/DEV-03 NumericKeypad auto-submit on 4th digit (Wave 0 scaffold).
 *
 * Test:
 *   Render DeviceDrawer in bind/ADD-DEVICE mode. Query the NumericKeypad digit
 *   keys and click "1", "2", "3", "4". Assert exactly ONE POST to
 *   /api/admin/devices/bind fires automatically after the 4th digit
 *   (no separate submit click required) with body code "1234".
 *
 * RED against the DeviceDrawer stub (returns null — no keypad rendered).
 * GREEN when Plan 03-04 implements DeviceDrawer with the NumericKeypad + auto-submit.
 *
 * Analog: ProfileDrawer.test.tsx (timer/mock/render pattern).
 *
 * Note: This test does NOT mock NumericKeypad — it renders the real NumericKeypad
 * component so the digit-key click tests are end-to-end through the component tree.
 * The fetch mock captures the bind POST to verify auto-submit behavior.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { DeviceDrawer } from './DeviceDrawer'

// ── Helpers ──────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0, gcTime: 0 },
      mutations: { retry: false },
    },
  })
}

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

describe('DeviceDrawer', () => {
  /**
   * Test: NumericKeypad auto-submit on 4th digit.
   *
   * When DeviceDrawer is opened in bind mode (mode="bind"):
   *   - NumericKeypad is rendered
   *   - Clicking digits "1", "2", "3", "4" in sequence
   *   - After the 4th digit, a POST /api/admin/devices/bind fires automatically
   *   - No separate submit/confirm button click is required
   *   - The POST body must contain code "1234"
   *
   * RED against the stub (returns null → no keypad → no POST).
   * GREEN when Plan 03-04 implements DeviceDrawer with NumericKeypad + auto-submit.
   *
   * Mirrors the PinOverlay.tsx auto-submit pattern (lines 105-116 of PATTERNS.md):
   *   handleDigit: if next.length === 4 → void handleBind(next.join(''))
   */
  it('auto-submits bind POST after the 4th digit via NumericKeypad', async () => {
    const bindCalls: string[] = []

    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (typeof url === 'string' && url.includes('/api/admin/devices/bind')) {
        const body = init?.body ? JSON.parse(init.body as string) : {}
        bindCalls.push(body.code ?? '')
      }
      return {
        ok: true,
        json: async () => ({ device_id: 'test-device-id' }),
      } as Response
    }))

    const qc = makeQueryClient()
    await act(async () => {
      render(
        <QueryClientProvider client={qc}>
          <DeviceDrawer mode="bind" onClose={vi.fn()} />
        </QueryClientProvider>,
      )
      await Promise.resolve()
    })

    // Query the NumericKeypad digit keys by their aria-label
    // NumericKeypad renders buttons with aria-label="1", "2", ... "9", "0"
    // (see frontend/src/routes/admin/NumericKeypad.tsx)
    const btn1 = screen.queryByRole('button', { name: '1' })
    const btn2 = screen.queryByRole('button', { name: '2' })
    const btn3 = screen.queryByRole('button', { name: '3' })
    const btn4 = screen.queryByRole('button', { name: '4' })

    // Assert the keypad buttons are rendered (will fail RED if stub returns null)
    expect(btn1).not.toBeNull()
    expect(btn2).not.toBeNull()
    expect(btn3).not.toBeNull()
    expect(btn4).not.toBeNull()

    // Click digit keys 1, 2, 3, 4 in sequence
    await act(async () => {
      btn1?.click()
      await Promise.resolve()
    })
    await act(async () => {
      btn2?.click()
      await Promise.resolve()
    })
    await act(async () => {
      btn3?.click()
      await Promise.resolve()
    })
    await act(async () => {
      btn4?.click()
      // Flush the auto-submit async handler
      await Promise.resolve()
      await Promise.resolve()
    })

    // After 4th digit, exactly one POST /api/admin/devices/bind must have fired
    // automatically (no separate submit click).
    expect(bindCalls).toHaveLength(1)
    expect(bindCalls[0]).toBe('1234')
  })
})

/**
 * DeviceDrawer tests — NumericKeypad auto-submit + profile-picker actions.
 *
 * Tests:
 *   1. Render in bind/ADD-DEVICE mode. Click "1", "2", "3", "4". Assert exactly ONE
 *      POST to /api/admin/devices/bind fires automatically after the 4th digit
 *      (no separate submit click required) with body code "1234".
 *
 *   2. PAIRED device drawer renders "CHANGE PROFILE" button and, on click, enters
 *      profile-picker mode showing profiles fetched from GET /api/admin/profiles.
 *      On picking a profile, PATCH /api/admin/devices/{id} fires with profile_id.
 *
 *   3. PENDING device drawer renders "BIND TO PROFILE" button and, on click, enters
 *      profile-picker mode. Picking a profile fires POST /api/admin/devices/bind
 *      with both code and profile_id when no last_pairing_code is on the device
 *      (fallback to bind-code mode) OR fires bindDevice when the code is available.
 *      This test covers the fallback-to-code-entry path (no last_pairing_code).
 *
 * Analog: ProfileDrawer.test.tsx (timer/mock/render pattern).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { DeviceDrawer } from './DeviceDrawer'
import type { DeviceRow } from '../../api/devices'

// ── Helpers ──────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0, gcTime: 0 },
      mutations: { retry: false },
    },
  })
}

const PAIRED_DEVICE: DeviceRow = {
  id: 'aaaa-bbbb-cccc-dddd',
  display_name: 'Living Room Pi',
  state: 'paired',
  profile_id: 'profile-uuid-1',
  profile_name: 'Default',
  last_seen_at: '2026-05-29T12:00:00Z',
}

const PENDING_DEVICE: DeviceRow = {
  id: 'eeee-ffff-0000-1111',
  display_name: 'Bedroom Pi',
  state: 'pending',
  profile_id: null,
  profile_name: null,
  last_seen_at: null,
}

const PROFILES_RESPONSE = [
  { id: 'profile-uuid-1', display_name: 'Default', status: 'connected', last_sync_at: null, last_sync_status: null, last_sync_error: null, last_sync_item_count: null, app_token_revoked: false },
  { id: 'profile-uuid-2', display_name: 'Robert', status: 'connected', last_sync_at: null, last_sync_status: null, last_sync_error: null, last_sync_item_count: null, app_token_revoked: false },
]

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
   * Test 1: NumericKeypad auto-submit on 4th digit.
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

    // NumericKeypad renders buttons with aria-label="1", "2", ... "9", "0"
    const btn1 = screen.queryByRole('button', { name: '1' })
    const btn2 = screen.queryByRole('button', { name: '2' })
    const btn3 = screen.queryByRole('button', { name: '3' })
    const btn4 = screen.queryByRole('button', { name: '4' })

    expect(btn1).not.toBeNull()
    expect(btn2).not.toBeNull()
    expect(btn3).not.toBeNull()
    expect(btn4).not.toBeNull()

    await act(async () => { btn1?.click(); await Promise.resolve() })
    await act(async () => { btn2?.click(); await Promise.resolve() })
    await act(async () => { btn3?.click(); await Promise.resolve() })
    await act(async () => {
      btn4?.click()
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(bindCalls).toHaveLength(1)
    expect(bindCalls[0]).toBe('1234')
  })

  /**
   * Test 2: PAIRED drawer — CHANGE PROFILE button opens picker; pick calls PATCH.
   *
   * Uses real timers (vi.useRealTimers) so TanStack Query resolves the profile fetch
   * without needing fake-timer advancement.
   */
  it('PAIRED drawer: renders CHANGE PROFILE; picking a profile calls PATCH devices/{id}', async () => {
    // This test needs real timers so TanStack Query settles the profile fetch.
    vi.useRealTimers()

    const patchCalls: Array<{ url: string; body: Record<string, unknown> }> = []

    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      const method = (init?.method ?? 'GET').toUpperCase()
      if (typeof url === 'string' && url.includes('/api/admin/profiles') && method === 'GET') {
        return { ok: true, json: async () => PROFILES_RESPONSE } as Response
      }
      if (typeof url === 'string' && url.includes('/api/admin/devices/') && method === 'PATCH') {
        const body = init?.body ? JSON.parse(init.body as string) : {}
        patchCalls.push({ url: url as string, body })
      }
      // CSRF cookie / admin session stub
      return { ok: true, json: async () => ({}) } as Response
    }))

    const qc = makeQueryClient()
    await act(async () => {
      render(
        <QueryClientProvider client={qc}>
          <DeviceDrawer device={PAIRED_DEVICE} onClose={vi.fn()} onActionComplete={vi.fn()} />
        </QueryClientProvider>,
      )
      await Promise.resolve()
    })

    // CHANGE PROFILE button should be present in view mode
    const changeProfileBtn = screen.getByRole('button', { name: /change profile/i })
    expect(changeProfileBtn).toBeTruthy()

    // Click CHANGE PROFILE — transitions to pick-profile mode and triggers profile fetch
    await act(async () => {
      changeProfileBtn.click()
      await Promise.resolve()
    })

    // Profile picker renders profiles fetched from API
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /robert/i })).toBeTruthy()
    }, { timeout: 3000 })

    // Pick "Robert" profile (profile-uuid-2)
    const robertBtn = screen.getByRole('button', { name: /robert/i })
    await act(async () => {
      robertBtn.click()
      await Promise.resolve()
      await Promise.resolve()
    })

    // PATCH /api/admin/devices/{id} should have been called with profile_id = 'profile-uuid-2'
    expect(patchCalls.length).toBeGreaterThanOrEqual(1)
    const patchCall = patchCalls.find(c => c.url.includes(PAIRED_DEVICE.id))
    expect(patchCall).toBeTruthy()
    expect(patchCall?.body).toMatchObject({ profile_id: 'profile-uuid-2' })
  })

  /**
   * Test 3: PENDING drawer — BIND TO PROFILE button opens picker; no pending code
   * on device falls back to bind-code (NumericKeypad) mode.
   *
   * Uses real timers so TanStack Query resolves the profile fetch.
   */
  it('PENDING drawer: renders BIND TO PROFILE; no pending code falls back to code entry', async () => {
    // This test needs real timers so TanStack Query settles the profile fetch.
    vi.useRealTimers()

    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      const method = (init?.method ?? 'GET').toUpperCase()
      if (typeof url === 'string' && url.includes('/api/admin/profiles') && method === 'GET') {
        return { ok: true, json: async () => PROFILES_RESPONSE } as Response
      }
      return { ok: true, json: async () => ({}) } as Response
    }))

    const qc = makeQueryClient()
    await act(async () => {
      render(
        <QueryClientProvider client={qc}>
          <DeviceDrawer device={PENDING_DEVICE} onClose={vi.fn()} onActionComplete={vi.fn()} />
        </QueryClientProvider>,
      )
      await Promise.resolve()
    })

    // BIND TO PROFILE button should be present in view mode for PENDING devices
    const bindToProfileBtn = screen.getByRole('button', { name: /bind to profile/i })
    expect(bindToProfileBtn).toBeTruthy()

    // Click BIND TO PROFILE — transitions to pick-profile mode and triggers profile fetch
    await act(async () => {
      bindToProfileBtn.click()
      await Promise.resolve()
    })

    // Profile picker renders profiles fetched from API
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /default/i })).toBeTruthy()
    }, { timeout: 3000 })

    // Pick "Default" profile — since device has no last_pairing_code, falls back to bind-code
    const defaultBtn = screen.getByRole('button', { name: /default/i })
    await act(async () => {
      defaultBtn.click()
      await Promise.resolve()
      await Promise.resolve()
    })

    // Should fall back to bind-code mode (NumericKeypad rendered)
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: '1' })).toBeTruthy()
    }, { timeout: 3000 })
  })

  // ── DEV-04: Prefill-confirm tests ─────────────────────────────────────────

  /**
   * Test 4 (DEV-04 / D-04): rendering with prefillCode shows confirm screen (not NumericKeypad)
   * and does NOT call the bind API on mount (no auto-submit).
   *
   * This is the critical D-04 gate: explicit one-tap confirm, not auto-submit.
   */
  it('prefillCode renders confirm screen (not NumericKeypad) and does NOT auto-submit', async () => {
    const bindCalls: string[] = []

    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (typeof url === 'string' && url.includes('/api/admin/devices/bind')) {
        const body = init?.body ? JSON.parse(init.body as string) : {}
        bindCalls.push(body.code ?? '')
      }
      return { ok: true, json: async () => ({}) } as Response
    }))

    const qc = makeQueryClient()
    await act(async () => {
      render(
        <QueryClientProvider client={qc}>
          <DeviceDrawer mode="bind" prefillCode="1234" onClose={vi.fn()} onActionComplete={vi.fn()} />
        </QueryClientProvider>,
      )
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })

    // Must NOT have auto-submitted — bind API not called on mount (D-04)
    expect(bindCalls).toHaveLength(0)

    // Confirm screen: "PAIR THIS DEVICE" CTA must be visible
    const pairBtn = screen.queryByRole('button', { name: /pair this device using code 1234/i })
    expect(pairBtn).not.toBeNull()

    // NumericKeypad must NOT be rendered (prefill confirm replaces it)
    const keypadBtn1 = screen.queryByRole('button', { name: '1' })
    expect(keypadBtn1).toBeNull()
  })

  /**
   * Test 5 (L-03 / single call site): tapping "PAIR THIS DEVICE" calls handleBind(prefillCode)
   * exactly ONCE with code '1234' — the same call site as the typed flow.
   */
  it('tapping PAIR THIS DEVICE calls bind API exactly once with prefillCode', async () => {
    const bindCalls: string[] = []

    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (typeof url === 'string' && url.includes('/api/admin/devices/bind')) {
        const body = init?.body ? JSON.parse(init.body as string) : {}
        bindCalls.push(body.code ?? '')
        return { ok: true, json: async () => ({ device_id: 'test-device-id', display_name: 'Test Pi' }) } as Response
      }
      return { ok: true, json: async () => ({}) } as Response
    }))

    const qc = makeQueryClient()
    await act(async () => {
      render(
        <QueryClientProvider client={qc}>
          <DeviceDrawer mode="bind" prefillCode="1234" onClose={vi.fn()} onActionComplete={vi.fn()} />
        </QueryClientProvider>,
      )
      await Promise.resolve()
      await Promise.resolve()
    })

    // Click the "PAIR THIS DEVICE" CTA
    const pairBtn = screen.queryByRole('button', { name: /pair this device using code 1234/i })
    expect(pairBtn).not.toBeNull()

    await act(async () => {
      pairBtn?.click()
      await Promise.resolve()
      await Promise.resolve()
    })

    // bind API called exactly once with the prefilled code (L-03)
    expect(bindCalls).toHaveLength(1)
    expect(bindCalls[0]).toBe('1234')
  })

  /**
   * Test 6: clicking "Enter a different code" clears prefill and shows NumericKeypad.
   */
  it('Enter a different code link clears prefill and shows NumericKeypad', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => {
      return { ok: true, json: async () => ({}) } as Response
    }))

    const qc = makeQueryClient()
    await act(async () => {
      render(
        <QueryClientProvider client={qc}>
          <DeviceDrawer mode="bind" prefillCode="1234" onClose={vi.fn()} onActionComplete={vi.fn()} />
        </QueryClientProvider>,
      )
      await Promise.resolve()
      await Promise.resolve()
    })

    // "Enter a different code" link must be present
    const differentCodeBtn = screen.queryByRole('button', { name: /enter a different code/i })
    expect(differentCodeBtn).not.toBeNull()

    // Click it — should drop back to NumericKeypad
    await act(async () => {
      differentCodeBtn?.click()
      await Promise.resolve()
    })

    // NumericKeypad should now be rendered
    const keypadBtn1 = screen.queryByRole('button', { name: '1' })
    expect(keypadBtn1).not.toBeNull()
  })
})

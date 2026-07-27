/**
 * PinOverlay tests — lock/unlock path (gruvax-2at).
 *
 * Regression coverage for: correct PIN entry while `isLocked` must invoke
 * `onUnlock` so AdminShell can clear its local `isLocked` state and dismiss
 * the overlay. Before the fix, nothing called `onUnlock` (it didn't exist)
 * and the overlay stayed mounted forever after a successful re-auth.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen } from '@testing-library/react'

import { PinOverlay } from './PinOverlay'

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: false })
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

async function tapDigits(digits: string[]) {
  for (const d of digits) {
    const btn = screen.getByRole('button', { name: d })
    await act(async () => {
      btn.click()
      await Promise.resolve()
    })
  }
}

describe('PinOverlay', () => {
  it('calls onUnlock on a correct PIN while isLocked (D-03c unlock path)', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (typeof url === 'string' && url.includes('/api/admin/login')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ csrf_token: 'test-csrf' }),
        } as Response
      }
      return { ok: true, status: 200, json: async () => ({}) } as Response
    }))

    const onUnlock = vi.fn()

    await act(async () => {
      render(<PinOverlay isLocked onUnlock={onUnlock} />)
      await Promise.resolve()
    })

    expect(screen.getByText('LOCKED')).toBeTruthy()

    await tapDigits(['1', '2', '3'])
    await act(async () => {
      screen.getByRole('button', { name: '4' }).click()
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(onUnlock).toHaveBeenCalledTimes(1)
  })

  it('does not require onUnlock when not locked (fresh login)', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (typeof url === 'string' && url.includes('/api/admin/login')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ csrf_token: 'test-csrf' }),
        } as Response
      }
      return { ok: true, status: 200, json: async () => ({}) } as Response
    }))

    await act(async () => {
      render(<PinOverlay />)
      await Promise.resolve()
    })

    expect(screen.getByText('ENTER PIN')).toBeTruthy()

    await tapDigits(['1', '2', '3'])
    await act(async () => {
      screen.getByRole('button', { name: '4' }).click()
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })

    // No error thrown from a missing onUnlock; overlay's own callback is optional.
    expect(screen.queryByRole('alert')).toBeNull()
  })
})

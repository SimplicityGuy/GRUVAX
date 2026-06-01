/**
 * useIdleTimer — Wave-0 RED tests (SRCH-09 / D-14/D-15).
 *
 * Tests:
 *   1. onIdle fires after the configured timeout with no interaction
 *   2. A pointermove event before the timeout resets the timer (onIdle does NOT fire early)
 *   3. A touchstart event before the timeout resets the timer (onIdle does NOT fire early)
 *   4. Unmounting the component cleans up listeners + timer (onIdle never fires after unmount)
 *
 * Uses vitest fake timers (matching PairView.test.tsx pattern).
 * These tests are RED until useIdleTimer.ts is created (Task 1 GREEN phase).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, renderHook } from '@testing-library/react'

describe('useIdleTimer', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: false })
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('fires onIdle after the configured timeout with no interaction', async () => {
    const { useIdleTimer } = await import('./useIdleTimer')

    const onIdle = vi.fn()
    const TIMEOUT_MS = 5000

    renderHook(() => useIdleTimer(TIMEOUT_MS, onIdle))

    expect(onIdle).not.toHaveBeenCalled()

    // Advance time to just before the timeout — should not fire
    await act(async () => {
      vi.advanceTimersByTime(TIMEOUT_MS - 1)
    })
    expect(onIdle).not.toHaveBeenCalled()

    // Advance past the timeout — should fire exactly once
    await act(async () => {
      vi.advanceTimersByTime(2)
    })
    expect(onIdle).toHaveBeenCalledTimes(1)
  })

  it('pointermove before timeout resets timer — onIdle does NOT fire at original deadline', async () => {
    const { useIdleTimer } = await import('./useIdleTimer')

    const onIdle = vi.fn()
    const TIMEOUT_MS = 5000

    renderHook(() => useIdleTimer(TIMEOUT_MS, onIdle))

    // Advance to halfway point, then dispatch pointermove
    await act(async () => {
      vi.advanceTimersByTime(TIMEOUT_MS / 2)
    })
    expect(onIdle).not.toHaveBeenCalled()

    // Dispatch pointermove — should reset the timer
    await act(async () => {
      document.dispatchEvent(new Event('pointermove'))
    })

    // Advance to where the original timeout would have fired (another half + small margin)
    await act(async () => {
      vi.advanceTimersByTime(TIMEOUT_MS / 2 + 100)
    })
    // Timer was reset, so onIdle should NOT have fired yet
    expect(onIdle).not.toHaveBeenCalled()

    // Now advance the remaining time to fire the reset timer
    await act(async () => {
      vi.advanceTimersByTime(TIMEOUT_MS - TIMEOUT_MS / 2 - 100)
    })
    // Should have fired once (after reset timer completes)
    expect(onIdle).toHaveBeenCalledTimes(1)
  })

  it('touchstart before timeout resets timer — onIdle does NOT fire early', async () => {
    const { useIdleTimer } = await import('./useIdleTimer')

    const onIdle = vi.fn()
    const TIMEOUT_MS = 4000

    renderHook(() => useIdleTimer(TIMEOUT_MS, onIdle))

    // Advance to 1 second in, then dispatch touchstart
    await act(async () => {
      vi.advanceTimersByTime(1000)
    })

    await act(async () => {
      document.dispatchEvent(new Event('touchstart'))
    })

    // Advance time past original deadline (3 more seconds: total 4001ms from start)
    await act(async () => {
      vi.advanceTimersByTime(3001)
    })
    // Timer was reset at 1s, so new deadline = 1s + 4s = 5s from start.
    // We're at 4001ms — NOT there yet.
    expect(onIdle).not.toHaveBeenCalled()

    // Advance remaining time to cross the reset deadline
    await act(async () => {
      vi.advanceTimersByTime(1000)
    })
    expect(onIdle).toHaveBeenCalledTimes(1)
  })

  it('cleanup on unmount — onIdle never fires after component unmounts', async () => {
    const { useIdleTimer } = await import('./useIdleTimer')

    const onIdle = vi.fn()
    const TIMEOUT_MS = 3000

    const { unmount } = renderHook(() => useIdleTimer(TIMEOUT_MS, onIdle))

    // Advance to halfway point
    await act(async () => {
      vi.advanceTimersByTime(TIMEOUT_MS / 2)
    })

    // Unmount — should clean up the timer
    unmount()

    // Advance past the full timeout — onIdle should NOT be called (timer cleared)
    await act(async () => {
      vi.advanceTimersByTime(TIMEOUT_MS + 1000)
    })
    expect(onIdle).not.toHaveBeenCalled()
  })
})

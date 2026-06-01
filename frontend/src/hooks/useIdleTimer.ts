/**
 * useIdleTimer — 15-minute kiosk idle timeout hook (SRCH-09 / D-14 / D-15).
 *
 * Fires `onIdle` after `timeoutMs` of no user interaction.
 * Resets the timer on: pointermove, pointerdown, keydown, touchstart.
 *
 * Design:
 *   - timerRef holds the active setTimeout ID (useRef avoids re-running the effect
 *     on every render — only re-runs when timeoutMs changes)
 *   - onIdleRef keeps the latest callback current without re-adding listeners (avoids
 *     stale closure issues with rapidly-changing callbacks)
 *   - Listeners added with { passive: true } for scroll/touch performance on Pi 5
 *   - Cleanup on unmount: removes all listeners + clears the timer
 *
 * Mount at KioskView top level only, NOT inside App or AdminShell (idle is kiosk-scoped).
 */

import { useEffect, useRef } from 'react'

const IDLE_EVENTS = ['pointermove', 'pointerdown', 'keydown', 'touchstart'] as const

export function useIdleTimer(timeoutMs: number, onIdle: () => void): void {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Keep the latest onIdle reference without re-adding document listeners
  const onIdleRef = useRef(onIdle)

  // Sync the latest onIdle callback into the ref (no listener re-registration needed)
  useEffect(() => {
    onIdleRef.current = onIdle
  })

  useEffect(() => {
    const reset = () => {
      if (timerRef.current !== null) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => {
        onIdleRef.current()
      }, timeoutMs)
    }

    // Register interaction listeners — passive for scroll/touch performance
    IDLE_EVENTS.forEach((event) =>
      document.addEventListener(event, reset, { passive: true }),
    )

    // Start the initial timer on mount
    reset()

    return () => {
      // Cleanup: remove all listeners + clear the pending timer
      IDLE_EVENTS.forEach((event) =>
        document.removeEventListener(event, reset),
      )
      if (timerRef.current !== null) clearTimeout(timerRef.current)
    }
  }, [timeoutMs]) // Only re-run when timeoutMs changes
}

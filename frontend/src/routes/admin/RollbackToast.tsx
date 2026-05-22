/**
 * RollbackToast — optimistic-rollback notification (UI-SPEC Surface 3, D-07).
 *
 * Shown on the admin device when a boundary edit is rejected by the server
 * and the optimistic update is reverted. The editor retains the attempted
 * values for retry (pendingChangeSet is NOT cleared — D-07).
 *
 * Design contract (locked from UI-SPEC Surface 3):
 *  - Copy: "Couldn't save that change — reverted." (sentence case, plain language)
 *  - Dismiss label: "Dismiss"
 *  - Icon: Lucide AlertTriangle at --gruvax-warning (caution, not error red)
 *  - Auto-dismiss: 4000ms from mount
 *  - Position: bottom-center, z-index above admin chrome
 *  - Animation: transform + opacity only (GPU-composited)
 *  - All colors: var(--gruvax-*) tokens — zero hardcoded hex
 *
 * Admin-surface only — this component must NEVER appear in KioskView.
 */

import { useEffect, useRef, useState } from 'react'
import './admin.css'

/** Inline Lucide AlertTriangle SVG — avoids adding a runtime dependency
 *  (codebase uses inline SVG for icons; see AdminShell.tsx for precedent). */
function AlertTriangleIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  )
}

interface RollbackToastProps {
  /** The message body (sentence case, plain language, no HTTP codes or jargon). */
  message: string
  /** Called when the toast should unmount (auto-dismiss or tap-to-dismiss). */
  onDismiss: () => void
}

export function RollbackToast({ message, onDismiss }: RollbackToastProps) {
  const [isExiting, setIsExiting] = useState(false)
  // Guard against double-dismiss (CR review WR-06): the 4000ms auto-dismiss timer
  // and a user tap can both fire handleDismiss, which would call onDismiss twice.
  const dismissed = useRef(false)

  /** Kick off the exit animation, then call onDismiss after it completes. */
  function handleDismiss() {
    if (dismissed.current) return
    dismissed.current = true
    setIsExiting(true)
    // toast-exit animation is 150ms (--gruvax-duration-fast); wait for it to finish.
    setTimeout(onDismiss, 150)
  }

  // Auto-dismiss: 4000ms from mount (UI-SPEC Surface 3)
  useEffect(() => {
    const t = setTimeout(handleDismiss, 4000)
    return () => clearTimeout(t)
    // handleDismiss is stable for the lifetime of this component
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div
      className={`toast${isExiting ? ' toast--exiting' : ''}`}
      role="alert"
      aria-live="assertive"
      aria-atomic="true"
    >
      <AlertTriangleIcon className="toast__icon" />
      <span className="toast__message">{message}</span>
      <button
        type="button"
        className="toast__dismiss"
        onClick={handleDismiss}
        aria-label="Dismiss notification"
      >
        Dismiss
      </button>
    </div>
  )
}

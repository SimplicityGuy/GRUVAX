/**
 * SyncToast — fixed top-right auto-dismiss notification for sync completion.
 *
 * UI-SPEC Surface 3 toast:
 *   - Fixed top-right, z-index --gruvax-z-admin (50)
 *   - --gruvax-success background, white text
 *   - role=status + aria-live=polite (non-urgent)
 *   - Auto-dismiss after 4 seconds
 *   - Slide in from right (entry), fade out (exit) per animation tokens
 *
 * Copy: "Sync complete — {N,###} records" — passed in as `message` prop.
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 */

import { useEffect, useState } from 'react'

interface SyncToastProps {
  message: string
  onDismiss: () => void
}

const AUTO_DISMISS_MS = 4000

export function SyncToast({ message, onDismiss }: SyncToastProps) {
  const [isExiting, setIsExiting] = useState(false)

  useEffect(() => {
    const exitTimer = setTimeout(() => {
      setIsExiting(true)
    }, AUTO_DISMISS_MS - 150) // Start exit animation 150ms before dismiss

    const dismissTimer = setTimeout(() => {
      onDismiss()
    }, AUTO_DISMISS_MS)

    return () => {
      clearTimeout(exitTimer)
      clearTimeout(dismissTimer)
    }
  }, [onDismiss])

  return (
    <div
      className={`sync-toast${isExiting ? ' sync-toast--exiting' : ''}`}
      role="status"
      aria-live="polite"
    >
      {message}
    </div>
  )
}

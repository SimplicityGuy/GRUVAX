/**
 * SwitchProfileConfirm — compact confirm modal for Switch-profile (Surface 6, D2-09).
 *
 * role="dialog", aria-modal="true", focus trap.
 * SWITCH → unbindProfile() → clearBoundProfile() → navigate('/select', { replace: true })
 * STAY HERE → onCancel() (dismiss without action)
 *
 * Design tokens only — no hardcoded hex.
 */

import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router'
import { unbindProfile } from '../../api/session'
import { useSessionStore } from '../../state/sessionStore'

interface SwitchProfileConfirmProps {
  onCancel: () => void
}

export function SwitchProfileConfirm({ onCancel }: SwitchProfileConfirmProps) {
  const navigate = useNavigate()
  const clearBoundProfile = useSessionStore((s) => s.clearBoundProfile)
  const dialogRef = useRef<HTMLDivElement>(null)
  const confirmBtnRef = useRef<HTMLButtonElement>(null)

  // Focus trap — focus the confirm button on mount, trap within dialog
  useEffect(() => {
    confirmBtnRef.current?.focus()

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onCancel()
        return
      }

      if (e.key !== 'Tab') return

      const dialog = dialogRef.current
      if (!dialog) return

      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((el) => !el.hasAttribute('disabled'))

      if (focusable.length === 0) return

      const first = focusable[0]
      const last = focusable[focusable.length - 1]

      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault()
          last.focus()
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onCancel])

  const handleConfirm = async () => {
    try {
      await unbindProfile()
    } catch {
      // Best-effort — proceed to /select even if the DELETE fails
    }
    clearBoundProfile()
    void navigate('/select', { replace: true })
  }

  const headingId = 'switch-profile-confirm-heading'

  return (
    <>
      {/* Scrim */}
      <div
        className="switch-confirm-scrim"
        aria-hidden="true"
        onClick={onCancel}
      />

      {/* Modal */}
      <div
        ref={dialogRef}
        className="switch-confirm-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={headingId}
      >
        <h2 id={headingId} className="switch-confirm-heading">
          Switch collection?
        </h2>
        <p className="switch-confirm-body">
          You'll be taken to the profile picker.
        </p>
        <div className="switch-confirm-actions">
          <button
            ref={confirmBtnRef}
            type="button"
            className="switch-confirm-btn switch-confirm-btn--confirm"
            onClick={() => { void handleConfirm() }}
          >
            SWITCH
          </button>
          <button
            type="button"
            className="switch-confirm-btn switch-confirm-btn--dismiss"
            onClick={onCancel}
          >
            STAY HERE
          </button>
        </div>
      </div>
    </>
  )
}

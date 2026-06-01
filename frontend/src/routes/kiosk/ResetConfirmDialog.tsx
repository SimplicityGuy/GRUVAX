/**
 * ResetConfirmDialog — no-PIN kiosk reset confirm modal (PRIV-04 / D-09 / D-11).
 *
 * Adapted from SwitchProfileConfirm.tsx:
 *   - role="alertdialog" (not "dialog") — per UI-SPEC a11y requirement for destructive actions
 *   - Initial focus on Cancel button (safer default for a destructive action — move to
 *     Cancel ref, not Confirm ref as in SwitchProfileConfirm)
 *   - Props: { onConfirm, onCancel } — NO navigation, NO API calls (L-05 / D-09)
 *   - The caller (KioskView) is responsible for calling clearSearch() + clear() on confirm
 *
 * Copywriting contract (08-UI-SPEC.md / D-11):
 *   - Heading: "Reset kiosk?"
 *   - Body: "This clears your recent searches. Your device stays connected."
 *   - Confirm: "CLEAR AND RESET"
 *   - Cancel: "KEEP RECENT SEARCHES"
 *
 * CSS class prefix: kiosk-reset-dialog-* (distinct from switch-confirm-*)
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 * Zero API calls, zero navigation — the component only invokes the passed callbacks.
 */

import { useEffect, useRef } from 'react'

interface ResetConfirmDialogProps {
  /** Called when user confirms the reset — caller handles clearSearch() + clear(). */
  onConfirm: () => void
  /** Called when user cancels (or presses Escape) — no action taken. */
  onCancel: () => void
}

export function ResetConfirmDialog({ onConfirm, onCancel }: ResetConfirmDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null)
  // Initial focus on Cancel button — safer default for a destructive action (D-11)
  const cancelBtnRef = useRef<HTMLButtonElement>(null)

  // Focus trap — focus Cancel on mount, trap within dialog, Escape closes
  useEffect(() => {
    cancelBtnRef.current?.focus()

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

  const headingId = 'kiosk-reset-dialog-heading'

  return (
    <>
      {/* Scrim — tapping outside cancels */}
      <div
        className="kiosk-reset-dialog-scrim"
        aria-hidden="true"
        onClick={onCancel}
      />

      {/* Modal — role="alertdialog" for destructive action (per UI-SPEC a11y) */}
      <div
        ref={dialogRef}
        className="kiosk-reset-dialog-modal"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={headingId}
      >
        <h2 id={headingId} className="kiosk-reset-dialog-heading">
          Reset kiosk?
        </h2>
        <p className="kiosk-reset-dialog-body">
          This clears your recent searches. Your device stays connected.
        </p>
        <div className="kiosk-reset-dialog-actions">
          {/* Confirm button — destructive, blue */}
          <button
            type="button"
            className="kiosk-reset-dialog-btn kiosk-reset-dialog-btn--confirm"
            onClick={onConfirm}
          >
            CLEAR AND RESET
          </button>
          {/* Cancel button — initial focus, low-emphasis */}
          <button
            ref={cancelBtnRef}
            type="button"
            className="kiosk-reset-dialog-btn kiosk-reset-dialog-btn--dismiss"
            onClick={onCancel}
          >
            KEEP RECENT SEARCHES
          </button>
        </div>
      </div>
    </>
  )
}

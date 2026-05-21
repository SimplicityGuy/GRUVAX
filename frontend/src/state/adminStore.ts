/**
 * Admin Zustand store — authentication state + pending change-set.
 *
 * Split from the main store (store.ts) because:
 *  1. Only ``pendingChangeSet`` is persisted to localStorage (via Zustand
 *     ``persist`` middleware) — mixing persisted and non-persisted slices
 *     in one store creates awkward partial-hydration issues.
 *  2. The admin store is only mounted when the user navigates to /admin;
 *     keeping it separate avoids loading localStorage overhead on the kiosk
 *     view which never needs admin state.
 *
 * Pattern: ``persist`` wraps only this store, partializing to ``pendingChangeSet``
 * so a session timeout or reload never loses in-progress boundary edits (D-04).
 */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ChangeSet } from '../api/types'

interface AdminStore {
  /** Whether the admin session is currently authenticated. */
  isLoggedIn: boolean

  /**
   * Unix timestamp (ms) when the idle session expires.
   * 0 when not logged in.
   */
  sessionExpiresAt: number

  /**
   * Unix timestamp (ms) of the absolute session hard cap.
   * 0 when not logged in.
   */
  hardCapExpiresAt: number

  /** CSRF token from the last successful login — echoed in X-CSRF-Token header. */
  csrfToken: string | null

  /**
   * In-progress boundary edits pending commit.
   * Persisted to localStorage so a timeout/reload preserves work (D-04).
   * null = no change-set in progress.
   */
  pendingChangeSet: ChangeSet | null

  /** Set after successful PIN login. */
  setAdminLoggedIn: (
    expiresAt: string,
    hardCapAt: string,
    csrfToken: string,
  ) => void

  /** Called on logout or session expiry. Clears auth state but NOT pendingChangeSet. */
  setAdminLoggedOut: () => void

  /**
   * Update the sliding expiry time (called by AdminShell on /session poll).
   * Only updates expiresAt — hard cap is immutable for the session lifetime.
   */
  refreshExpiry: (expiresAt: string) => void

  /** Replace the entire pending change-set (or clear it with null). */
  setPendingChangeSet: (cs: ChangeSet | null) => void
}

export const useAdminStore = create<AdminStore>()(
  persist(
    (set) => ({
      isLoggedIn: false,
      sessionExpiresAt: 0,
      hardCapExpiresAt: 0,
      csrfToken: null,
      pendingChangeSet: null,

      setAdminLoggedIn: (expiresAt, hardCapAt, csrfToken) =>
        set({
          isLoggedIn: true,
          sessionExpiresAt: new Date(expiresAt).getTime(),
          hardCapExpiresAt: new Date(hardCapAt).getTime(),
          csrfToken,
        }),

      setAdminLoggedOut: () =>
        set({
          isLoggedIn: false,
          sessionExpiresAt: 0,
          hardCapExpiresAt: 0,
          csrfToken: null,
          // pendingChangeSet intentionally NOT cleared — preserved across re-auth
        }),

      refreshExpiry: (expiresAt) =>
        set({ sessionExpiresAt: new Date(expiresAt).getTime() }),

      setPendingChangeSet: (cs) => set({ pendingChangeSet: cs }),
    }),
    {
      name: 'gruvax-admin',
      // Persist ONLY the pending change-set — auth state must not survive a page
      // reload (the HttpOnly cookie handles session continuity; the store's
      // isLoggedIn is derived on mount by polling /api/admin/session).
      partialize: (state) => ({ pendingChangeSet: state.pendingChangeSet }),
    },
  ),
)

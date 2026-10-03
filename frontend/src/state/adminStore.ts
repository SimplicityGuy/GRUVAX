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
import type { AdminSession, ChangeSet, ReshuffleDraft } from '../api/types'

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
  setAdminLoggedIn: (session: AdminSession, csrfToken: string) => void

  /** Called on logout or session expiry. Clears auth state but NOT pendingChangeSet. */
  setAdminLoggedOut: () => void

  /** Refresh both server-authoritative deadlines, using durations to avoid clock skew. */
  refreshExpiry: (session: AdminSession) => void

  /** Replace the entire pending change-set (or clear it with null). */
  setPendingChangeSet: (cs: ChangeSet | null) => void

  /**
   * In-progress wizard/reshuffle draft persisted to localStorage (D-05, D-06, D-07).
   * Set to null when the wizard commits successfully or the user discards.
   * Intentionally survives setAdminLoggedOut so the owner can resume after re-auth (Pitfall 2).
   */
  reshuffleDraft: ReshuffleDraft | null

  /** Replace the reshuffle draft (or clear it with null). */
  setReshuffleDraft: (draft: ReshuffleDraft | null) => void
}

/** Keep BOTH deadlines on one browser-clock anchor; server timestamps are informational. */
function sessionDeadlines(session: AdminSession) {
  const now = Date.now()
  return {
    sessionExpiresAt: now + session.expires_in_seconds * 1000,
    hardCapExpiresAt: now + session.hard_cap_in_seconds * 1000,
  }
}

export const useAdminStore = create<AdminStore>()(
  persist(
    (set) => ({
      isLoggedIn: false,
      sessionExpiresAt: 0,
      hardCapExpiresAt: 0,
      csrfToken: null,
      pendingChangeSet: null,

      setAdminLoggedIn: (session, csrfToken) =>
        set({ isLoggedIn: true, ...sessionDeadlines(session), csrfToken }),

      setAdminLoggedOut: () =>
        set({
          isLoggedIn: false,
          sessionExpiresAt: 0,
          hardCapExpiresAt: 0,
          csrfToken: null,
          // pendingChangeSet intentionally NOT cleared — preserved across re-auth
        }),

      refreshExpiry: (session) => set(sessionDeadlines(session)),

      setPendingChangeSet: (cs) => set({ pendingChangeSet: cs }),

      reshuffleDraft: null,
      setReshuffleDraft: (draft) => set({ reshuffleDraft: draft }),
    }),
    {
      name: 'gruvax-admin',
      // Persist ONLY the pending change-set and reshuffle draft — auth state must not survive
      // a page reload (the HttpOnly cookie handles session continuity; the store's isLoggedIn
      // is derived on mount by polling /api/admin/session).
      partialize: (state) => ({
        pendingChangeSet: state.pendingChangeSet,
        reshuffleDraft: state.reshuffleDraft,
      }),
    },
  ),
)

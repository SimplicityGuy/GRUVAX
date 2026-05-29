/**
 * Session Zustand store — browse-binding state (Plan 02-06).
 *
 * Holds the server-side session data: which profiles exist, which is bound.
 * Modeled on adminStore.ts shape but simpler (no persistence — session state
 * is server-authoritative and bootstrapped on every app mount via GET /api/session).
 *
 * Split from adminStore.ts for the same reason adminStore.ts is split from
 * store.ts: the kiosk view should never load admin auth overhead.
 */

import { create } from 'zustand'
import type { ProfileSummary, SessionData } from '../api/session'

interface SessionStore {
  /** Number of active profiles (non-deleted). */
  profileCount: number

  /**
   * UUID string of the currently bound profile, or null when unbound.
   * Named to match backend JSON key (bound_profile_id).
   */
  boundProfileId: string | null

  /** Full profile list from GET /api/session. */
  profiles: ProfileSummary[]

  /**
   * Update the store from a GET /api/session response.
   * Called by the App.tsx bootstrap effect on mount.
   */
  setSession: (data: SessionData) => void

  /**
   * Clear the bound profile without a server call.
   * Called after DELETE /api/session/bind succeeds so the SPA can navigate
   * to /select before the next GET /api/session response.
   */
  clearBoundProfile: () => void
}

export const useSessionStore = create<SessionStore>()((set) => ({
  profileCount: 0,
  boundProfileId: null,
  profiles: [],

  setSession: (data: SessionData) =>
    set({
      profileCount: data.profile_count,
      boundProfileId: data.bound_profile_id,
      profiles: data.profiles,
    }),

  clearBoundProfile: () =>
    set({
      boundProfileId: null,
    }),
}))

/**
 * Session Zustand store — browse-binding state (Plan 02-06).
 *
 * Holds the server-side session data: which profiles exist, which is bound.
 * Modeled on adminStore.ts shape but simpler (no persistence — session state
 * is server-authoritative and bootstrapped on every app mount via GET /api/session).
 *
 * Split from adminStore.ts for the same reason adminStore.ts is split from
 * store.ts: the kiosk view should never load admin auth overhead.
 *
 * Phase 6 (06-02): adds device lifecycle UI state.
 * - revokePending: boolean — set by triggerRevoke() (idempotent); consumed by App.tsx
 *   as the SINGLE terminal-revoke handler (D-06). Fires from SSE device_revoked event
 *   AND from client.ts 403 device_revoked intercept — whichever arrives first.
 * - reassignBanner: string|null — set by setReassignBanner(name) when a
 *   device_reassigned SSE event arrives; auto-dismissed after ~2.5s in KioskView.
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
   * True when a terminal device-revoke event has been received (from SSE
   * device_revoked or a 403 device_revoked response). Consumed by App.tsx's
   * global revoke effect — the SINGLE handler (D-06).
   *
   * Set via triggerRevoke() (idempotent — second call is a no-op).
   * Cleared via resetRevoke() after the navigate('/pair') completes.
   */
  revokePending: boolean

  /**
   * Display name of the new profile after a device_reassigned event.
   * Non-null triggers the "MOVED TO <name>" banner in KioskView.
   * Auto-dismissed after ~2.5s via setReassignBanner(null).
   */
  reassignBanner: string | null

  /**
   * Update the store from a GET /api/session response.
   * Called by the App.tsx bootstrap effect on mount.
   */
  setSession: (data: SessionData) => void

  /**
   * Clear the bound profile without a server call.
   * Called after DELETE /api/session/bind succeeds so the SPA can navigate
   * to /select before the next GET /api/session response.
   * Also called by the terminal-revoke handler (App.tsx) before navigate('/pair').
   */
  clearBoundProfile: () => void

  /**
   * Signal a terminal device-revoke (idempotent).
   *
   * Sets revokePending: true ONLY if it is currently false. A second call
   * (racing SSE + 403) is a no-op — the kiosk exits exactly once (D-06,
   * T-06-06).
   *
   * Callable outside React (getState().triggerRevoke()) so client.ts can
   * fire it without mounting any component.
   */
  triggerRevoke: () => void

  /**
   * Clear revokePending after the navigate('/pair') completes.
   * Called by App.tsx's effect so a future re-pair can be revoked again.
   */
  resetRevoke: () => void

  /**
   * Set the reassign banner display name (D-08, D-09).
   * Pass null to dismiss.
   */
  setReassignBanner: (name: string | null) => void
}

export const useSessionStore = create<SessionStore>()((set, get) => ({
  profileCount: 0,
  boundProfileId: null,
  profiles: [],
  revokePending: false,
  reassignBanner: null,

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

  triggerRevoke: () => {
    // Idempotent: only flip when currently false (D-06 / T-06-06)
    if (!get().revokePending) {
      set({ revokePending: true })
    }
  },

  resetRevoke: () => set({ revokePending: false }),

  setReassignBanner: (name: string | null) => set({ reassignBanner: name }),
}))

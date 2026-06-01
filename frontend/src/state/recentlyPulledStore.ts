/**
 * recentlyPulledStore — session-only recently-pulled chip strip (SRCH-09 / PRIV-01).
 *
 * Backed by sessionStorage under the key 'gruvax-kiosk-recent' so the list:
 *   - Survives an accidental soft reload (D-13)
 *   - Clears automatically on a hard Chromium restart (tab close / process exit — D-13)
 *   - Is NEVER written to localStorage (PRIV-01 isolation from 'gruvax-admin' key)
 *
 * Separate from useAdminStore (different key, different storage engine) — mixing them
 * would create partial-hydration issues and violate PRIV-01.
 *
 * addItem semantics (D-07):
 *   - Dedupes by release_id: re-adding an existing item removes the old copy first
 *   - Prepends the new item (most-recent-first order)
 *   - Caps at 8 items (.slice(0, 8) after prepend)
 */

import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

/** Identity-only shape stored per item. No stale LocateResult stored (Pitfall 5). */
export interface RecentItem {
  release_id: number
  title: string
  primary_artist: string
  catalog_number: string
}

interface RecentlyPulledStore {
  /** Most-recent-first list, capped at 8 (D-07). */
  items: RecentItem[]

  /**
   * Add a located record to the front of the list.
   * Dedupes by release_id (re-adding moves to front, no duplicate).
   * Caps at 8 items after prepend.
   */
  addItem: (item: RecentItem) => void

  /** Clear the entire list — called by Reset kiosk + idle timeout. */
  clear: () => void
}

export const useRecentlyPulledStore = create<RecentlyPulledStore>()(
  persist(
    (set) => ({
      items: [],

      addItem: (item) =>
        set((state) => {
          // Remove existing entry with the same release_id (dedupe), then prepend and cap
          const filtered = state.items.filter((r) => r.release_id !== item.release_id)
          return { items: [item, ...filtered].slice(0, 8) }
        }),

      clear: () => set({ items: [] }),
    }),
    {
      name: 'gruvax-kiosk-recent',
      // sessionStorage: cleared on tab close / hard Chromium restart (PRIV-01 / D-13)
      storage: createJSONStorage(() => sessionStorage),
      // No partialize — the entire slice is session-only; everything belongs in sessionStorage
    },
  ),
)

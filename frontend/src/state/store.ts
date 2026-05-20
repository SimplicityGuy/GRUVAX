import { create } from 'zustand'
import type { CubeRef, SearchResult } from '../api/types'

interface HighlightState {
  primaryCube: CubeRef | null
}

interface GruvaxStore {
  /** Current search query string */
  query: string
  setQuery: (q: string) => void

  /** The selected search result's release_id (drives locate call) */
  selectedReleaseId: number | null
  setSelectedReleaseId: (id: number | null) => void

  /** The selected result object (for UI display) */
  selectedResult: SearchResult | null
  setSelectedResult: (result: SearchResult | null) => void

  /** Primary cube highlight state — set after /api/locate resolves */
  highlight: HighlightState
  setHighlightCube: (cube: CubeRef | null) => void

  /** Animation token — incremented on each highlight change to trigger animations */
  animationToken: number

  /** Clear the search field and all highlight state */
  clearSearch: () => void
}

export const useGruvaxStore = create<GruvaxStore>((set) => ({
  query: '',
  setQuery: (q) => set({ query: q }),

  selectedReleaseId: null,
  setSelectedReleaseId: (id) => set({ selectedReleaseId: id }),

  selectedResult: null,
  setSelectedResult: (result) => set({ selectedResult: result }),

  highlight: { primaryCube: null },
  setHighlightCube: (cube) =>
    set((s) => ({
      highlight: { primaryCube: cube },
      animationToken: s.animationToken + 1,
    })),

  animationToken: 0,

  clearSearch: () =>
    set({
      query: '',
      selectedReleaseId: null,
      selectedResult: null,
      highlight: { primaryCube: null },
      animationToken: 0,
    }),
}))

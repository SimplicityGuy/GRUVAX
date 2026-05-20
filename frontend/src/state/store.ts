import { create } from 'zustand'
import type { CubeRef, LocateResult, SearchResult, SubInterval } from '../api/types'

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

  /** Label span — all cubes occupied by the label (sorted unit_id,row,col) */
  labelSpan: CubeRef[]

  /** Sub-cube position interval from /api/locate — null when only cube-level */
  subCubeInterval: SubInterval | null

  /** Position confidence 0.0–1.0 — drives bar opacity and "~" cue */
  confidence: number

  /**
   * Set the full locate result atomically (CUBE-04 / D-01).
   * Increments animationToken unconditionally — even on same-cube re-selection
   * (Pitfall D) — so GSAP timeline always fires.
   */
  setLocateResult: (result: LocateResult) => void

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

  labelSpan: [],
  subCubeInterval: null,
  confidence: 0,

  setLocateResult: (result) =>
    set((s) => ({
      highlight: { primaryCube: result.primary_cube },
      labelSpan: result.label_span,
      subCubeInterval: result.sub_cube_interval,
      confidence: result.confidence,
      // Token increments unconditionally — even same-cube re-selection fires GSAP (Pitfall D)
      animationToken: s.animationToken + 1,
    })),

  animationToken: 0,

  clearSearch: () =>
    set({
      query: '',
      selectedReleaseId: null,
      selectedResult: null,
      highlight: { primaryCube: null },
      labelSpan: [],
      subCubeInterval: null,
      confidence: 0,
      animationToken: 0,
    }),
}))

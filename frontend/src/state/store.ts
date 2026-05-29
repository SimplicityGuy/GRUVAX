import { create } from 'zustand'
import type { CubeRef, LocateResult, SearchResult, SubInterval } from '../api/types'

interface HighlightState {
  primaryCube: CubeRef | null
}

/** Identifies a Kallax cube by its shelf coordinates. */
export interface ShimmerCube {
  unit: number
  row: number
  col: number
}

/**
 * SSE connectivity state (Phase 4 / D-10).
 * bannerVisible is a stub for the deferred Offline-Banner slice (Plan 04);
 * set false always this phase.
 */
interface ConnectivityState {
  sseConnected: boolean
  lastSeenAt: number
  bannerVisible: false
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

  /**
   * True when the last locate result returned HTTP 200 with primary_cube=null and
   * confidence=0 — meaning the release IS in the collection but no cube boundary
   * covers its label (Plan 09 / D-12: zero-boundary profile affordance).
   *
   * Set only inside setLocateResult — never derived from bare null primaryCube
   * so a cleared/empty search box never triggers the affordance.
   * Reset to false on clearSearch and when a real cube is present.
   */
  shelfLayoutUnavailable: boolean

  /** Clear the search field and all highlight state */
  clearSearch: () => void

  // ── Phase 4: SSE connectivity + shimmer (D-10, D-03) ────────────────────

  /** SSE connectivity state — set by EventSource onopen / onerror / server_shutdown */
  connectivity: ConnectivityState

  /**
   * Set SSE connected state (D-10).
   * When connecting (connected=true), stamps lastSeenAt=Date.now().
   */
  setSseConnected: (connected: boolean) => void

  /**
   * Cubes currently in shimmer state (admin is editing them — Phase 4 admin_editing event).
   * Cleared by boundary_changed (D-03: primary on-commit clear) or after shimmerExpiresAt TTL.
   */
  shimmerCubes: ShimmerCube[]

  /**
   * Epoch ms at which all shimmer cubes expire (Date.now() + 60_000).
   * Consumed by the idle-shimmer sweep in Plan 04 (D-03 60s safety).
   */
  shimmerExpiresAt: number

  /**
   * Start shimmer for the given cubes (admin_editing event, editing=true).
   * Stamps shimmerExpiresAt = Date.now() + 60_000 (D-03 TTL).
   */
  setShimmerCubes: (cubes: ShimmerCube[]) => void

  /**
   * Clear shimmer for the given cubes (boundary_changed or admin_editing editing=false).
   * D-03: primary on-commit clear — removes only the matching unit-row-col keys.
   */
  clearShimmerCubes: (cubes: ShimmerCube[]) => void
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
      // Plan 09 / D-12: signal that the release IS in the collection but no cube boundary
      // covers its label. Derived ONLY from a locate result — never from bare null primaryCube —
      // so a cleared/empty search box does not trigger the affordance.
      shelfLayoutUnavailable: result.primary_cube == null && result.confidence === 0,
    })),

  animationToken: 0,

  shelfLayoutUnavailable: false,

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
      shelfLayoutUnavailable: false,
    }),

  // ── Phase 4: SSE connectivity + shimmer ─────────────────────────────────

  connectivity: { sseConnected: false, lastSeenAt: 0, bannerVisible: false },

  setSseConnected: (connected) =>
    set((s) => ({
      connectivity: {
        ...s.connectivity,
        sseConnected: connected,
        // Stamp lastSeenAt only when transitioning to connected (D-10)
        lastSeenAt: connected ? Date.now() : s.connectivity.lastSeenAt,
      },
    })),

  shimmerCubes: [],
  shimmerExpiresAt: 0,

  setShimmerCubes: (cubes) =>
    set({
      shimmerCubes: cubes,
      // D-03 TTL: shimmer expires in 60s even if no boundary_changed arrives
      shimmerExpiresAt: Date.now() + 60_000,
    }),

  clearShimmerCubes: (cubes) =>
    set((s) => {
      const keysToRemove = new Set(cubes.map((c) => `${c.unit}:${c.row}:${c.col}`))
      return {
        shimmerCubes: s.shimmerCubes.filter(
          (c) => !keysToRemove.has(`${c.unit}:${c.row}:${c.col}`),
        ),
      }
    }),
}))

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import gsap from 'gsap'
import { fetchCubesWithFill, fetchUnits, searchCollection } from '../../api/client'
import type { CubeRef } from '../../api/types'
import { useGruvaxStore } from '../../state/store'
import { CubeContentsPanel } from './CubeContentsPanel'
import { ResultsList } from './ResultsList'
import { SearchBox } from './SearchBox'
import { ShelfGrid } from './ShelfGrid'
import { ShelfLabel } from './ShelfLabel'
import './kiosk.css'

const SHELF_NAMES = ['SHELF A', 'SHELF B', 'SHELF C', 'SHELF D']

/**
 * Full-page kiosk view: header + search + results + shelf grid.
 * Orchestrates SearchBox ↔ ResultsList ↔ ShelfGrid via Zustand store.
 *
 * Per 01-UI-SPEC.md §Layout / Kiosk View — Overall Page Layout.
 *
 * Phase 2 (CUBE-08): GSAP selection-lands timeline fires on animationToken change.
 * Animated nodes are resolved by data-attribute/class selectors scoped to the
 * .shelf-area container — no forwardRef plumbing needed.
 */
export function KioskView() {
  const { highlight, animationToken, labelSpan, subCubeInterval, confidence, clearSearch, setQuery } =
    useGruvaxStore()
  const [debouncedQuery, setDebouncedQuery] = useState('')
  // Cube-tap state for the contents panel (CUBE-09, D-14)
  const [tappedCube, setTappedCube] = useState<CubeRef | null>(null)
  // The query whose results the user explicitly dismissed (by selecting a row).
  // The dropdown is derived as open when there is a query that hasn't been
  // dismissed — so it reopens automatically on the next keystroke (new query)
  // and collapses after a pick, without a set-state-in-effect.
  const [dismissedQuery, setDismissedQuery] = useState<string | null>(null)

  // Loading indicator state — shown only after >300ms in flight (SRCH-05)
  const [showLoading, setShowLoading] = useState(false)
  const loadingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [hasSearchError, setHasSearchError] = useState(false)

  // ── GSAP refs (Task 3 / CUBE-08) ───────────────────────────────────────
  /** Container ref — all GSAP selectors are scoped to this element */
  const shelfAreaRef = useRef<HTMLDivElement | null>(null)
  /** Holds the active GSAP timeline for hard-cancel on new selection (D-06) */
  const timelineRef = useRef<gsap.core.Timeline | null>(null)

  // Fetch units from API (drives grid)
  const { data: unitsData } = useQuery({
    queryKey: ['units'],
    queryFn: fetchUnits,
    staleTime: Infinity,
  })

  // Fetch all cube boundaries once — used to render empty state (CUBE-05) + fill bars (CUBE-07)
  const { data: cubesData } = useQuery({
    queryKey: ['cubes'],
    queryFn: fetchCubesWithFill,
    staleTime: Infinity,
  })

  // Build a Set<"unitId-row-col"> of empty cubes for O(1) lookup in ShelfGrid
  const emptyCubes = useMemo<Set<string>>(() => {
    if (!cubesData) return new Set()
    return new Set(
      cubesData.cubes
        .filter((cb) => cb.is_empty)
        .map((cb) => `${cb.unit_id}-${cb.row}-${cb.col}`),
    )
  }, [cubesData])

  // Build a Map<"unitId-row-col", fillLevel> for FillBar rendering in ShelfGrid (CUBE-07)
  const fillLevels = useMemo<Map<string, number>>(() => {
    if (!cubesData) return new Map()
    return new Map(
      cubesData.cubes
        .filter((cb) => !cb.is_empty && cb.fill_level > 0)
        .map((cb) => [`${cb.unit_id}-${cb.row}-${cb.col}`, cb.fill_level]),
    )
  }, [cubesData])

  // TanStack Query for search — fires on debouncedQuery change (SRCH-01)
  const {
    data: searchData,
    isFetching,
    isError,
  } = useQuery({
    queryKey: ['search', debouncedQuery],
    queryFn: () => searchCollection(debouncedQuery, 10),
    enabled: debouncedQuery.trim().length > 0,
    staleTime: 30_000,
  })

  // Delayed loading indicator — only show if in flight >300ms (SRCH-05)
  useEffect(() => {
    if (loadingTimerRef.current) clearTimeout(loadingTimerRef.current)

    if (isFetching && debouncedQuery.trim().length > 0) {
      loadingTimerRef.current = setTimeout(() => {
        setShowLoading(true)
      }, 300)
    } else {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- resets a timer-driven loading indicator when the query settles; not derivable during render
      setShowLoading(false)
    }
    return () => {
      if (loadingTimerRef.current) clearTimeout(loadingTimerRef.current)
    }
  }, [isFetching, debouncedQuery])

  // Track search errors
  useEffect(() => {
    if (isError) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- transient error-flash cue driven by the query's error state; cleared by the timeout below
      setHasSearchError(true)
      // Clear error flash after 400ms (per spec)
      const t = setTimeout(() => setHasSearchError(false), 400)
      return () => clearTimeout(t)
    } else {
      setHasSearchError(false)
    }
  }, [isError])

  // Clear highlight when query is empty
  useEffect(() => {
    if (debouncedQuery.trim().length === 0) {
      clearSearch()
    }
  }, [debouncedQuery, clearSearch])

  // Derived: the dropdown is open when there is a query that the user has not
  // dismissed by selecting a row. A new query (different string) reopens it
  // automatically; an explicit selection records the query as dismissed.
  const resultsOpen =
    debouncedQuery.trim().length > 0 && dismissedQuery !== debouncedQuery

  // "Did you mean" tap (D-10): set the query the user sees AND trigger the
  // search immediately. setQuery drives the (controlled) SearchBox input;
  // setDebouncedQuery runs the corrected search without waiting for debounce.
  const handleDidYouMean = (term: string) => {
    setQuery(term)
    setDebouncedQuery(term)
  }

  // ── GSAP selection-lands timeline (CUBE-08 / D-05 / D-06) ─────────────
  //
  // Fires on every animationToken increment (new selection or re-selection).
  // Resolves animated nodes by data-attribute/class selectors scoped to
  // shelfAreaRef — no forwardRef plumbing needed (02-UI-SPEC.md §Ref Strategy).
  //
  // Timeline: span fade-in → primary pulse → bar slide-in ≤600ms (SC-3).
  // Hard-cancel: kill() on each run (D-06 — no cross-fade between selections).
  // Will-change: .is-animating toggled on/off (never permanently set — Pitfall 16).
  //
  // useLayoutEffect: DOM nodes for the new selection are mounted before querying.
  useLayoutEffect(() => {
    // Hard-cancel previous in-flight timeline (D-06)
    timelineRef.current?.kill()

    const container = shelfAreaRef.current
    if (!container) return

    // Resolve animated nodes by stable selectors (Task 2 adds these hooks)
    const primaryCube = container.querySelector<HTMLElement>('[data-state="lit"]')
    const barNode = container.querySelector<HTMLElement>('.sub-cube-bar')
    const bandNodes = Array.from(
      container.querySelectorAll<HTMLElement>('.span-underlay__band'),
    )

    // Track resolved nodes for cleanup
    const resolvedNodes: Array<HTMLElement | null> = [
      primaryCube,
      barNode,
      ...bandNodes,
    ]

    // Apply will-change during animation window (Pi 5 compositor optimization)
    resolvedNodes.forEach((n) => n?.classList.add('is-animating'))

    // Reset elements to start state before building new timeline
    bandNodes.forEach((band) => gsap.set(band, { opacity: 0 }))

    const isSingleton =
      subCubeInterval != null &&
      subCubeInterval.start === 0 &&
      subCubeInterval.end === 1

    if (barNode) {
      if (isSingleton) {
        // Singleton: reset opacity (cross-fade in step 3 variant)
        gsap.set(barNode, { opacity: 0 })
      } else {
        // Normal: reset scaleX for slide-in
        gsap.set(barNode, { scaleX: 0, transformOrigin: 'left center' })
      }
    }

    const tl = gsap.timeline({
      onComplete: () => {
        // Release will-change after animation settles (Pitfall 16)
        resolvedNodes.forEach((n) => n?.classList.remove('is-animating'))
      },
    })

    // Step 1: Span underlay fade-in (0ms → 150ms) — skip if no bands
    if (bandNodes.length > 0) {
      tl.fromTo(
        bandNodes,
        { opacity: 0 },
        { opacity: 0.6, duration: 0.15, ease: 'power2.out' },
      )
    }

    // Step 2a: Primary cube spring pulse — scale out (150ms → 250ms)
    if (primaryCube) {
      tl.fromTo(
        primaryCube,
        { scale: 1 },
        { scale: 1.04, duration: 0.1, ease: 'back.out(1.7)' },
        bandNodes.length > 0 ? '+=0' : '0',
      )
      // Step 2b: Primary cube settle — scale back (250ms → 350ms)
      tl.to(primaryCube, { scale: 1, duration: 0.1, ease: 'power2.inOut' })
    }

    // Step 3: Bar animation — overlapped -=0.10 with step 2b (300ms → 500ms)
    if (barNode) {
      if (isSingleton) {
        // Singleton variant: cross-fade in (no scaleX slide — D-02)
        tl.fromTo(
          barNode,
          { opacity: 0 },
          { opacity: 0.18, duration: 0.2, ease: 'power2.out' },
          '-=0.10',
        )
      } else {
        // Normal: slide-in from left (scaleX 0→1)
        tl.fromTo(
          barNode,
          { scaleX: 0, transformOrigin: 'left center' },
          { scaleX: 1, duration: 0.2, ease: 'power2.out' },
          '-=0.10',
        )
      }
    }

    timelineRef.current = tl

    return () => {
      // Hard-cancel on effect cleanup (new animationToken or unmount)
      tl.kill()
      // Release will-change on interrupt — never leave compositor layer permanently
      resolvedNodes.forEach((n) => n?.classList.remove('is-animating'))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [animationToken])

  const searchResults = searchData?.items ?? []
  const showNoResults =
    debouncedQuery.trim().length > 0 &&
    !isFetching &&
    searchResults.length === 0 &&
    !isError

  const units = unitsData?.units ?? []
  // Sort units by ordering field
  const sortedUnits = [...units].sort((a, b) => a.ordering - b.ordering)

  return (
    <div className="kiosk-page">
      {/* Header */}
      <header className="kiosk-header">
        <span className="kiosk-header__wordmark">GRUVAX</span>
      </header>

      {/* Main content */}
      <main className="kiosk-content">
        {/* Search section — contains search box + floating results list */}
        <div className="kiosk-search-section">
          <SearchBox
            onDebouncedQuery={setDebouncedQuery}
            isLoading={showLoading}
            hasError={hasSearchError}
          />
          <ResultsList
            items={debouncedQuery.trim().length > 0 ? searchResults : []}
            showNoResults={showNoResults}
            didYouMean={searchData?.did_you_mean ?? null}
            open={resultsOpen}
            onResultSelect={() => setDismissedQuery(debouncedQuery)}
            onDidYouMean={handleDidYouMean}
          />
        </div>

        {/* Shelf area — N×(4×4) grid — shelfAreaRef for GSAP selector scope */}
        <div className="shelf-area" ref={shelfAreaRef}>
          {sortedUnits.map((unit, idx) => (
            <div key={unit.id} className="shelf-section">
              <ShelfLabel name={SHELF_NAMES[idx] ?? `SHELF ${idx + 1}`} />
              <ShelfGrid
                unit={unit}
                shelfIndex={idx}
                litCube={highlight.primaryCube}
                emptyCubes={emptyCubes}
                labelSpan={labelSpan}
                subCubeInterval={subCubeInterval}
                confidence={confidence}
                fillLevels={fillLevels}
                onCubeTap={setTappedCube}
              />
            </div>
          ))}

          {/* Fallback: show placeholder grid if units not loaded yet */}
          {sortedUnits.length === 0 && (
            <>
              {[0, 1].map((idx) => (
                <div key={idx} className="shelf-section">
                  <ShelfLabel name={SHELF_NAMES[idx] ?? `SHELF ${idx + 1}`} />
                  <ShelfGrid
                    unit={{ id: idx + 1, display_name: '', rows: 4, cols: 4, ordering: idx + 1 }}
                    shelfIndex={idx}
                    litCube={highlight.primaryCube}
                    emptyCubes={emptyCubes}
                    labelSpan={labelSpan}
                    subCubeInterval={subCubeInterval}
                    confidence={confidence}
                    fillLevels={fillLevels}
                    onCubeTap={setTappedCube}
                  />
                </div>
              ))}
            </>
          )}
        </div>
      </main>

      {/* Cube-contents panel (CUBE-09, D-14) — bottom sheet, slides up on cube tap */}
      <CubeContentsPanel
        cube={tappedCube}
        onDismiss={() => setTappedCube(null)}
      />
    </div>
  )
}

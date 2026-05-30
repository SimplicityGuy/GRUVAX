import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import gsap from 'gsap'
import { fetchCubesWithFill, fetchUnits, locateRelease, searchCollection } from '../../api/client'
import type { CubeRef } from '../../api/types'
import { useGruvaxStore, type ShimmerCube } from '../../state/store'
import { useSessionStore } from '../../state/sessionStore'
import { getSession } from '../../api/session'
import { CubeContentsPanel } from './CubeContentsPanel'
import { EmptyCollectionState } from './EmptyCollectionState'
import { ReauthBanner } from './ReauthBanner'
import { ResultsList } from './ResultsList'
import { ShelfLayoutNotConfigured } from './ShelfLayoutNotConfigured'
import { SearchBox } from './SearchBox'
import { ShelfGrid } from './ShelfGrid'
import { ShelfLabel } from './ShelfLabel'
import { StalenessBar } from './StalenessBar'
import { SwitchProfileButton } from './SwitchProfileButton'
import './ReauthBanner.css'
import './StalenessBar.css'
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
  const { highlight, animationToken, labelSpan, subCubeInterval, confidence, clearSearch, setQuery, shelfLayoutUnavailable, selectedReleaseId } =
    useGruvaxStore()
  // Phase 4 / D-01/D-03/RTM-04: reactive shimmer state from Zustand
  const shimmerCubes = useGruvaxStore((s) => s.shimmerCubes)
  const shimmerExpiresAt = useGruvaxStore((s) => s.shimmerExpiresAt)
  // Phase 2 / D2-04: session store for bound profile
  const boundProfileId = useSessionStore((s) => s.boundProfileId)
  const profiles = useSessionStore((s) => s.profiles)
  const queryClient = useQueryClient()
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

  // Health query — drives kiosk staleness banner (OBS-06, D-01).
  // 60s refetch is allowed here: this is the banner data source, not admin telemetry;
  // D-11's no-polling rule applies to the diagnostics page, not the kiosk health banner.
  // When health is unavailable (offline), sync_age_seconds is null → banner hides.
  const { data: healthData } = useQuery<{ sync_age_seconds?: number | null }>({
    queryKey: ['health'],
    queryFn: () => fetch('/api/health').then((r) => r.json()),
    staleTime: 60_000,
    refetchInterval: 60_000,
  })

  // Session re-auth polling (D4-08): low-frequency refetch so a freshly-revoked PAT
  // surfaces the ReauthBanner within ≤5 min without a manual reload.
  // Uses the same getSession() function as App.tsx bootstrap; stores result locally
  // so the kiosk can derive needs_reauth without extending the Zustand store shape.
  const setSession = useSessionStore((s) => s.setSession)
  const { data: sessionData } = useQuery({
    queryKey: ['session'],
    queryFn: async () => {
      const data = await getSession()
      // Keep the session store in sync so bound profile ID stays current
      setSession(data)
      return data
    },
    staleTime: 4 * 60_000,       // 4 min — treat as fresh for 4 min
    refetchInterval: 5 * 60_000, // re-poll every 5 min (D4-08 ≤5 min requirement)
    refetchOnWindowFocus: true,
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

  // Phase 4 / D-01/RTM-04: derive a Set<"unit-row-col"> from the shimmerCubes array for O(1)
  // lookup in ShelfGrid. Keyed on shimmerCubes so it only recomputes when the array reference
  // changes (Zustand replaces the array on every setShimmerCubes / clearShimmerCubes call).
  const shimmerSet = useMemo<Set<string>>(
    () => new Set(shimmerCubes.map((c) => `${c.unit}-${c.row}-${c.col}`)),
    [shimmerCubes],
  )

  // Phase 4 / D-03: 60s client TTL sweeper — safety clear for abandoned edits.
  // When shimmerCubes is non-empty, schedule a timeout for (shimmerExpiresAt - now).
  // On fire, clear all current shimmer cubes via getState() (avoids stale closure —
  // Pitfall 5). Timer is cancelled on change/unmount so no double-clear happens.
  // The primary clear path (boundary_changed → clearShimmerCubes) is in the SSE
  // consumer above — this sweeper only fires if the commit never arrives (~60s idle).
  useEffect(() => {
    if (shimmerCubes.length === 0) return

    const msUntilExpiry = shimmerExpiresAt - Date.now()
    if (msUntilExpiry <= 0) {
      // Already expired — clear immediately
      useGruvaxStore.getState().clearShimmerCubes(useGruvaxStore.getState().shimmerCubes)
      return
    }

    const timer = setTimeout(() => {
      useGruvaxStore.getState().clearShimmerCubes(useGruvaxStore.getState().shimmerCubes)
    }, msUntilExpiry)

    return () => {
      clearTimeout(timer)
    }
  }, [shimmerCubes, shimmerExpiresAt])

  // TanStack Query for search — fires on debouncedQuery change (SRCH-01)
  // D2-04: pass bound profile_id as query param (02-03-SUMMARY: search uses query param)
  const {
    data: searchData,
    isFetching,
    isError,
  } = useQuery({
    queryKey: ['search', debouncedQuery, boundProfileId],
    queryFn: () => searchCollection(debouncedQuery, 10, boundProfileId ?? undefined),
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

  // ── Phase 4: SSE consumer — boundary_changed live re-render (RTM-01, ADMN-11) ──
  //
  // D2-04 (Phase 2): SSE URL is per-profile: /api/events/{profile_id} (path param).
  // If no profile is bound (during bootstrap or after unbind), the SSE connection
  // is not opened — Effect re-runs when boundProfileId changes (in dep array).
  //
  // On connect: mark sseConnected + resync all boundary-derived queries (D-11).
  // On boundary_changed: invalidate the affected query keys so TanStack Query
  //   refetches in the background → re-renders affected cubes (D-04).
  // On admin_editing: shimmer the indicated cubes (setShimmerCubes / clearShimmerCubes).
  // On server_hello: resync + invalidate settings (handles server restart).
  // On server_shutdown: mark sseConnected false (the EventSource auto-reconnects).
  // On error: mark sseConnected false — do NOT call es.close() here (Pitfall 4).
  // Cleanup: es.close() in the return — the ONLY place close is called.
  //
  // All store mutations use useGruvaxStore.getState() inside event handlers to
  // avoid stale closures (Pitfall 5 — do NOT read from the outer destructure).
  useEffect(() => {
    // D-05 + D-11: re-locate the active selection if one is set.
    // Uses .getState() to avoid stale closures (Pitfall 5).
    // D2-04: pass boundProfileId so locate also carries the profile param.
    const relocateActiveSelection = () => {
      const { selectedReleaseId } = useGruvaxStore.getState()
      if (selectedReleaseId != null) {
        // Read boundProfileId from session store at call-time (stale-closure safe)
        const pid = useSessionStore.getState().boundProfileId
        void locateRelease(selectedReleaseId, pid ?? undefined).then((result) => {
          // Re-read setLocateResult via getState to ensure it's current (Pitfall 5)
          useGruvaxStore.getState().setLocateResult(result)
        })
      }
    }

    const resync = () => {
      // D-08 (CR WR-01 / verifier Gap 2): the kiosk consumer invalidates ONLY
      // kiosk-owned keys. Admin keys (['admin', ...]) are never mounted on the
      // kiosk route, so invalidating them here is dead code that risks racing an
      // admin optimistic update if the same SPA ever shares this consumer.
      void queryClient.invalidateQueries({ queryKey: ['units'] })
      void queryClient.invalidateQueries({ queryKey: ['cubes'] })
      // D-05 + D-11: if a selection is active, re-locate it after reconnect
      // so the highlight reflects the boundary that may have changed while disconnected.
      relocateActiveSelection()
    }

    // D2-04: per-profile SSE URL — only open when a profile is bound.
    // If boundProfileId is null (unbound), skip SSE and mark disconnected.
    const currentProfileId = useSessionStore.getState().boundProfileId
    if (!currentProfileId) {
      useGruvaxStore.getState().setSseConnected(false)
      return
    }

    const es = new EventSource(`/api/events/${currentProfileId}`)

    es.onopen = () => {
      useGruvaxStore.getState().setSseConnected(true)
      resync()
    }

    es.onerror = () => {
      // Mark disconnected — EventSource auto-reconnects; do NOT call es.close() (Pitfall 4)
      useGruvaxStore.getState().setSseConnected(false)
    }

    // boundary_changed: admin edit committed → re-render affected cubes (D-04, D-03)
    // IN-02: wrapped in try/catch so a malformed or mis-keyed frame degrades gracefully
    // instead of throwing an uncaught TypeError that terminates the handler.
    es.addEventListener('boundary_changed', (e: MessageEvent) => {
      try {
        const { cube_ids } = JSON.parse(e.data) as {
          cube_ids: ShimmerCube[]
          change_set_id: string
        }
        // Invalidate kiosk-owned query keys only (D-08 — see resync note above)
        void queryClient.invalidateQueries({ queryKey: ['cubes'] })
        void queryClient.invalidateQueries({ queryKey: ['units'] })
        for (const c of cube_ids) {
          void queryClient.invalidateQueries({
            queryKey: ['cube-contents', c.unit, c.row, c.col],
          })
        }
        // D-03: primary on-commit shimmer clear
        useGruvaxStore.getState().clearShimmerCubes(cube_ids)
        // D-05: if visitor has an active selection, re-run locate so the highlight
        // follows the record to its new cube. setLocateResult bumps animationToken
        // → existing GSAP useLayoutEffect fires → old cube fades off, new cube
        // springs on (D-06 re-glow). No new animation code needed.
        relocateActiveSelection()
      } catch (err) {
        console.error('[SSE] boundary_changed parse error — degrading gracefully', err)
      }
    })

    // admin_editing: admin has opened the editor for these cubes → shimmer them
    // IN-02: wrapped in try/catch so a mis-keyed frame does not propagate as
    // an uncaught TypeError into the Zustand reducers (cube_ids: undefined risk).
    es.addEventListener('admin_editing', (e: MessageEvent) => {
      try {
        const { cube_ids, editing } = JSON.parse(e.data) as {
          cube_ids: ShimmerCube[]
          editing: boolean
        }
        if (editing) {
          useGruvaxStore.getState().setShimmerCubes(cube_ids)
        } else {
          useGruvaxStore.getState().clearShimmerCubes(cube_ids)
        }
      } catch (err) {
        console.error('[SSE] admin_editing parse error — degrading gracefully', err)
      }
    })

    // server_hello: server (re)started → resync all data + settings
    es.addEventListener('server_hello', () => {
      resync()
      void queryClient.invalidateQueries({ queryKey: ['admin', 'settings'] })
    })

    // server_shutdown: server going down → mark disconnected (auto-reconnect handles it)
    es.addEventListener('server_shutdown', () => {
      useGruvaxStore.getState().setSseConnected(false)
    })

    // Cleanup: close the connection on unmount (the ONLY es.close() call — Pitfall 4)
    return () => {
      es.close()
    }
    // D2-04: re-run effect when boundProfileId changes so the SSE URL updates
  }, [queryClient, boundProfileId])

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

  // D2-03: detect bound-but-unsynced profile (empty collection).
  // Signal: the bound profile's last_sync_item_count is 0 (or null) and
  // last_sync_status is not 'completed'/'ok' (never successfully synced).
  // This is distinct from "search returned no matches" (NoResultsRow).
  const boundProfile = profiles.find((p) => p.id === boundProfileId) ?? null

  // Derive needs_reauth: prefer server's authoritative needs_reauth field (D4-08);
  // fall back to reading app_token_revoked from the bound profile in the session store.
  const needsReauth =
    sessionData?.needs_reauth ??
    (boundProfile?.app_token_revoked ?? false)

  const isEmptyCollection =
    boundProfile != null &&
    (boundProfile.last_sync_item_count == null || boundProfile.last_sync_item_count === 0) &&
    boundProfile.last_sync_status !== 'completed' &&
    boundProfile.last_sync_status !== 'ok'

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
          {/* D2-03: EmptyCollectionState replaces results area for unsynced profiles */}
          {isEmptyCollection ? (
            <EmptyCollectionState />
          ) : (
            <ResultsList
              items={debouncedQuery.trim().length > 0 ? searchResults : []}
              showNoResults={showNoResults}
              didYouMean={searchData?.did_you_mean ?? null}
              open={resultsOpen}
              onResultSelect={() => setDismissedQuery(debouncedQuery)}
              onDidYouMean={handleDidYouMean}
            />
          )}
        </div>

        {/* Staleness banner (OBS-06, D-01) — above the grid, never overlaying it.
            Hidden when offline (health null) or sync_age <= 14d. */}
        <StalenessBar syncAgeSeconds={healthData?.sync_age_seconds ?? null} />

        {/* Re-auth banner (D4-08, D4-10): non-blocking, appears when bound profile's
            PAT is revoked. CRITICAL: search input, cube grid, and all kiosk
            interactivity remain live — this banner is purely informational. */}
        {needsReauth && <ReauthBanner profileName={boundProfile?.display_name} />}

        {/* Plan 09 / D-12: shelf layout not configured affordance.
            Shown when a selected result IS in the collection (HTTP 200 locate)
            but the bound profile has zero cube boundaries (null cube, 0 confidence).
            NOT shown for: empty/unsynced collections, cleared search, genuine no-results. */}
        {shelfLayoutUnavailable && !isEmptyCollection && selectedReleaseId != null && (
          <ShelfLayoutNotConfigured />
        )}

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
                shimmerCubes={shimmerSet}
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
                    shimmerCubes={shimmerSet}
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

      {/* D2-09: persistent Switch-profile corner button (2+ profiles only) */}
      <SwitchProfileButton />
    </div>
  )
}

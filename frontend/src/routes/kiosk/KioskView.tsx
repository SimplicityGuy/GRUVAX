import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchUnits, searchCollection } from '../../api/client'
import { useGruvaxStore } from '../../state/store'
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
 */
export function KioskView() {
  const { highlight, clearSearch } = useGruvaxStore()
  const [debouncedQuery, setDebouncedQuery] = useState('')

  // Loading indicator state — shown only after >300ms in flight (SRCH-05)
  const [showLoading, setShowLoading] = useState(false)
  const loadingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [hasSearchError, setHasSearchError] = useState(false)

  // Fetch units from API (drives grid)
  const { data: unitsData } = useQuery({
    queryKey: ['units'],
    queryFn: fetchUnits,
    staleTime: Infinity,
  })

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
      setShowLoading(false)
    }
    return () => {
      if (loadingTimerRef.current) clearTimeout(loadingTimerRef.current)
    }
  }, [isFetching, debouncedQuery])

  // Track search errors
  useEffect(() => {
    if (isError) {
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
          />
        </div>

        {/* Shelf area — N×(4×4) grid */}
        <div className="shelf-area">
          {sortedUnits.map((unit, idx) => (
            <div key={unit.id} className="shelf-section">
              <ShelfLabel name={SHELF_NAMES[idx] ?? `SHELF ${idx + 1}`} />
              <ShelfGrid
                unit={unit}
                shelfIndex={idx}
                litCube={highlight.primaryCube}
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
                  />
                </div>
              ))}
            </>
          )}
        </div>
      </main>
    </div>
  )
}

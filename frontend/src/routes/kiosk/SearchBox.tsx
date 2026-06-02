import { useRef } from 'react'
import { useGruvaxStore } from '../../state/store'

interface SearchBoxProps {
  /** Called when the debounced query changes (after ~250ms idle) */
  onDebouncedQuery: (q: string) => void
  /** True when a request has been in flight for >300ms (SRCH-05) */
  isLoading: boolean
  /** True if the last API call resulted in an error */
  hasError: boolean
  /**
   * True when SSE connection is lost — greys + disables the input and swaps the placeholder
   * to "Search unavailable while offline" (OFF-02, D-06).
   * Loading/error affordances and the clear-X are also suppressed while offline.
   */
  isOffline?: boolean
}

/**
 * Kiosk search input with:
 *  - Debounce ~250ms before firing onDebouncedQuery (SRCH-06)
 *  - Clear-X button (≥44×44px tap target) that empties query + clears highlight (SRCH-03)
 *  - Loading indicator shown ONLY after >300ms in flight (3-dot pulse) (SRCH-05)
 *  - Error flash on API failure (SRCH-02 error path)
 *
 * Per 01-UI-SPEC.md §Search Box Component Contract.
 * All colors/fonts/motion from kiosk.css tokens — no hardcoded hex here.
 */
export function SearchBox({ onDebouncedQuery, isLoading, hasError, isOffline = false }: SearchBoxProps) {
  // store.query is the single source of truth for the input value, so external
  // setters (e.g. a "did you mean" tap calling setQuery) update the field too.
  const { query, setQuery, clearSearch } = useGruvaxStore()
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value
    setQuery(val)

    // Debounce: fire onDebouncedQuery ~250ms after last keystroke (SRCH-06)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      onDebouncedQuery(val)
    }, 250)
  }

  const handleClear = () => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    clearSearch()
    onDebouncedQuery('')
  }

  // While offline: suppress loading, error, and clear-X (no query interaction — OFF-02, D-06)
  const showClearX = query.length > 0 && !isLoading && !isOffline
  const showLoading = isLoading && !isOffline

  const boxClass = [
    'search-box',
    hasError && !isOffline ? 'search-box--error' : '',
    isOffline ? 'search-box--offline' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className={boxClass} role="search">
      {/* Magnifier icon — non-interactive */}
      <svg
        className="search-box__icon"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>

      <input
        className="search-box__input"
        type="search"
        value={query}
        onChange={handleChange}
        placeholder={isOffline ? 'Search unavailable while offline' : 'Type artist, title, label or catalog#'}
        aria-label="Search vinyl collection"
        autoComplete="off"
        autoCorrect="off"
        spellCheck={false}
        disabled={isOffline}
      />

      {/* Loading indicator — only after >300ms in flight (SRCH-05); suppressed offline */}
      {showLoading && (
        <div className="search-box__action" aria-label="Searching…">
          <div className="search-box__loading" role="status">
            <div className="search-box__dot" />
            <div className="search-box__dot" />
            <div className="search-box__dot" />
          </div>
        </div>
      )}

      {/* Clear-X button — ≥44×44px tap target (SRCH-03); suppressed offline */}
      {showClearX && (
        <button
          type="button"
          className="search-box__action"
          onClick={handleClear}
          aria-label="Clear search"
        >
          ×
        </button>
      )}
    </div>
  )
}

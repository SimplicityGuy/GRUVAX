import { useEffect } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { illuminateRecord, locateRelease } from '../../api/client'
import type { SearchResult } from '../../api/types'
import { useGruvaxStore } from '../../state/store'
import { useSessionStore } from '../../state/sessionStore'
import { DidYouMean } from './DidYouMean'
import { NoResultsRow } from './NoResultsRow'
import { ResultRow } from './ResultRow'

interface ResultsListProps {
  items: SearchResult[]
  /** True when query is non-empty but items is empty */
  showNoResults: boolean
  /** Trigram-similarity suggestion from /api/search (SRCH-07/D-11).
   *  Rendered below NoResultsRow; null = no suggestion or pg_trgm absent. */
  didYouMean?: string | null
  /**
   * Whether the dropdown is open. Reopened by the parent on each new query and
   * set false after an explicit selection so the list collapses once the user
   * picks a record (auto-select-top keeps it open; only an explicit tap/Enter
   * dismisses it). Defaults to true so other call sites are unaffected.
   */
  open?: boolean
  /** Called when the user explicitly selects a row (tap or Enter) so the parent
   *  can collapse the dropdown. Not called by auto-select-top. */
  onResultSelect?: () => void
  /** Called when the user taps the "did you mean" suggestion (D-10). The parent
   *  sets the search query AND triggers the corrected search. */
  onDidYouMean?: (term: string) => void
}

/**
 * Animated results list with top-result auto-highlight (SRCH-02, CUBE-02).
 *
 * On search result arrival:
 *  1. Auto-selects top result (SRCH-02).
 *  2. Calls /api/locate → sets highlight.primaryCube in store.
 *  3. Framer Motion AnimatePresence handles enter/exit.
 *
 * On tap of a different row → calls /api/locate for that release.
 * On tap of DidYouMean row → calls setQuery(term) to set the search box
 *   (D-10: no silent auto-correct — user explicitly initiates the search).
 * On clear (empty items, empty query) → handled by parent; store is cleared.
 *
 * Per 01-UI-SPEC.md §Results List Component Contract + §Top-result auto-highlight.
 */
export function ResultsList({
  items,
  showNoResults,
  didYouMean,
  open = true,
  onResultSelect,
  onDidYouMean,
}: ResultsListProps) {
  const { selectedResult, setSelectedResult, setSelectedReleaseId, setHighlightCube, setLocateResult } =
    useGruvaxStore()

  const isVisible = open && (items.length > 0 || showNoResults)

  // Auto-select top result on arrival (SRCH-02 / D-08).
  // Key the effect on the top result's release_id — NOT the `items` array
  // reference — so it fires only when the top result actually changes, not on
  // every parent re-render that hands down a new array identity (WR-02).
  const topReleaseId = items.length > 0 ? items[0].release_id : null
  useEffect(() => {
    if (topReleaseId == null) return
    const top = items[0]
    setSelectedResult(top)
    setSelectedReleaseId(top.release_id)
    // Fire locate for top result — feed full result into store (CUBE-04/Phase 2).
    // D2-04: locate's profile_id query param is REQUIRED (locate.py), so pass the
    // bound profile or every call 422s and is swallowed (no cube, no affordance).
    // Read at call-time via getState() to stay stale-closure-safe (matches KioskView).
    const topPid = useSessionStore.getState().boundProfileId
    void locateRelease(top.release_id, topPid ?? undefined)
      .then((result) => {
        setLocateResult(result)
        // Phase 6: fire-and-forget illuminate — never block locate path (D-01)
        void illuminateRecord(result).catch(() => {
          // Swallow — broker may be in degraded mode
        })
      })
      .catch(() => {
        setHighlightCube(null)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topReleaseId])

  const handleSelect = (result: SearchResult) => {
    // Collapse the dropdown immediately on an explicit pick — don't wait for
    // the async locate (fixes: autocomplete list lingered over the grid).
    onResultSelect?.()
    setSelectedResult(result)
    setSelectedReleaseId(result.release_id)
    // D2-04: pass the bound profile_id (required query param) — see auto-locate note above.
    const pid = useSessionStore.getState().boundProfileId
    void locateRelease(result.release_id, pid ?? undefined)
      .then((located) => {
        setLocateResult(located)
        // Phase 6: fire-and-forget illuminate after explicit select (D-01)
        void illuminateRecord(located).catch(() => {
          // Swallow — broker may be in degraded mode
        })
      })
      .catch(() => {
        setHighlightCube(null)
      })
  }

  // D-10: onTap sets the search query — user sees the corrected term in the
  // search box and explicitly triggers the new search. No silent auto-correct.
  const handleDidYouMeanTap = (term: string) => {
    onDidYouMean?.(term)
  }

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          className="results-list"
          role="listbox"
          aria-label="Search results"
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.2, ease: [0.0, 0.0, 0.2, 1] }}
        >
          <div className="results-list__scroll">
            {showNoResults && items.length === 0 ? (
              <>
                <NoResultsRow />
                {didYouMean && (
                  <DidYouMean suggestion={didYouMean} onTap={handleDidYouMeanTap} />
                )}
              </>
            ) : (
              items.map((item) => (
                <ResultRow
                  key={item.release_id}
                  result={item}
                  isSelected={selectedResult?.release_id === item.release_id}
                  onSelect={handleSelect}
                />
              ))
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

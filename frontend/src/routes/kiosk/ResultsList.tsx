import { useEffect } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { locateRelease } from '../../api/client'
import type { SearchResult } from '../../api/types'
import { useGruvaxStore } from '../../state/store'
import { NoResultsRow } from './NoResultsRow'
import { ResultRow } from './ResultRow'

interface ResultsListProps {
  items: SearchResult[]
  /** True when query is non-empty but items is empty */
  showNoResults: boolean
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
 * On clear (empty items, empty query) → handled by parent; store is cleared.
 *
 * Per 01-UI-SPEC.md §Results List Component Contract + §Top-result auto-highlight.
 */
export function ResultsList({ items, showNoResults }: ResultsListProps) {
  const { selectedResult, setSelectedResult, setSelectedReleaseId, setHighlightCube } =
    useGruvaxStore()

  const isVisible = items.length > 0 || showNoResults

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
    // Fire locate for top result
    void locateRelease(top.release_id)
      .then((result) => {
        setHighlightCube(result.primary_cube)
      })
      .catch(() => {
        setHighlightCube(null)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topReleaseId])

  const handleSelect = (result: SearchResult) => {
    setSelectedResult(result)
    setSelectedReleaseId(result.release_id)
    void locateRelease(result.release_id)
      .then((located) => {
        setHighlightCube(located.primary_cube)
      })
      .catch(() => {
        setHighlightCube(null)
      })
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
              <NoResultsRow />
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

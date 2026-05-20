import type { SearchResult } from '../../api/types'

interface ResultRowProps {
  result: SearchResult
  isSelected: boolean
  onSelect: (result: SearchResult) => void
}

/**
 * Single result row in the results list.
 *
 * Layout (per 01-UI-SPEC.md §Result row anatomy):
 *   Line 1: Artist · Title  (Space Grotesk 16px, --gruvax-text-body)
 *   Line 2: Label  [CATALOG# in DM Mono]
 *
 * Selected state: --gruvax-blue-faint background + 2px yellow left border.
 * Colors/fonts from CSS tokens only.
 */
export function ResultRow({ result, isSelected, onSelect }: ResultRowProps) {
  const handleClick = () => onSelect(result)

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onSelect(result)
    }
  }

  const primaryLine = result.primary_artist
    ? `${result.primary_artist} · ${result.title}`
    : result.title

  return (
    <div
      className={`result-row${isSelected ? ' result-row--selected' : ''}`}
      role="option"
      aria-selected={isSelected}
      tabIndex={0}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
    >
      <div className="result-row__primary">{primaryLine}</div>
      <div className="result-row__secondary">
        <span className="result-row__label">{result.label}</span>
        {result.catalog_number && (
          <span className="result-row__catalog">{result.catalog_number}</span>
        )}
      </div>
    </div>
  )
}

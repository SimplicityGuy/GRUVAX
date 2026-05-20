/**
 * Displayed when a non-empty search returns zero results (SRCH-04).
 * Copywriting per 01-UI-SPEC.md §Copywriting Contract.
 * Colors from CSS tokens only.
 */
export function NoResultsRow() {
  return (
    <div className="no-results-row">
      {/* 24px magnifier with slash — inline SVG, color via CSS var */}
      <svg
        className="no-results-row__icon"
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
        <line x1="4" y1="4" x2="18" y2="18" />
      </svg>
      <div className="no-results-row__text">
        <span className="no-results-row__heading">No records found</span>
        <span className="no-results-row__body">
          Try a different search or check the label name.
        </span>
      </div>
    </div>
  )
}

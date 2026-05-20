/**
 * Displays a single tappable "Did you mean X?" row below NoResultsRow
 * when the API returns a trigram-similarity suggestion (SRCH-07, D-10/D-11).
 *
 * Tapping sets the search box to the suggestion term — no silent auto-correct
 * (D-10: user explicitly initiates the corrected search).
 *
 * Accessibility:
 *   - role="button" + tabIndex={0}: keyboard reachable
 *   - aria-label="Search for {suggestion}": screen-reader label
 *   - Enter / Space key handler mirrors ResultRow.tsx keyboard pattern
 *   - min-height: 44px (WCAG 2.5.5 touch target minimum)
 *
 * Colors from CSS tokens only — no hardcoded hex.
 */

interface DidYouMeanProps {
  suggestion: string
  onTap: (term: string) => void
}

export function DidYouMean({ suggestion, onTap }: DidYouMeanProps) {
  const handleClick = () => {
    onTap(suggestion)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onTap(suggestion)
    }
  }

  return (
    <div
      className="did-you-mean"
      role="button"
      tabIndex={0}
      aria-label={`Search for ${suggestion}`}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
    >
      {/* Question-mark-circle icon — color via --gruvax-warning token */}
      <svg
        className="did-you-mean__icon"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="10" />
        <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
        <line x1="12" y1="17" x2="12.01" y2="17" />
      </svg>
      <div className="did-you-mean__text">
        <span className="did-you-mean__copy">
          {'Did you mean '}
          <strong className="did-you-mean__term">
            {suggestion.toUpperCase()}
          </strong>
          {'?'}
        </span>
      </div>
    </div>
  )
}

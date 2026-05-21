/**
 * AlphaRail — vertical A–Z quick-jump rail for the admin cubes grid.
 *
 * 32 px wide × 44 px per button. Tapping a letter scrolls to (or navigates to)
 * the first cube whose label_first starts with that letter (case-insensitive).
 * Letters with no match are rendered at reduced opacity (still tappable).
 *
 * Token-driven styles only — no hardcoded hex.
 *
 * Props:
 *   activeLetters — Set of letters that have at least one cube.
 *   onLetterTap   — Callback with the tapped letter (uppercase).
 */

const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('')

interface AlphaRailProps {
  /** Set of uppercase letters that have at least one matching cube. */
  activeLetters: Set<string>
  /** Called with the tapped letter (uppercase). */
  onLetterTap: (letter: string) => void
}

export function AlphaRail({ activeLetters, onLetterTap }: AlphaRailProps) {
  return (
    <nav
      className="alpha-rail"
      aria-label="Jump to label"
    >
      {ALPHABET.map((letter) => {
        const hasMatch = activeLetters.has(letter)
        return (
          <button
            key={letter}
            type="button"
            className={`alpha-rail-btn${hasMatch ? '' : ' alpha-rail-btn--inactive'}`}
            onClick={() => onLetterTap(letter)}
            aria-label={`Jump to labels starting with ${letter}`}
            aria-disabled={!hasMatch}
          >
            {letter}
          </button>
        )
      })}
    </nav>
  )
}

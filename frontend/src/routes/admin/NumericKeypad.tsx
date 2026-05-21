/**
 * NumericKeypad — pure presentational 3×4 keypad for PIN entry.
 *
 * Layout (UI-SPEC §A):
 *   1  2  3
 *   4  5  6
 *   7  8  9
 *   *  0  ⌫
 *
 * The * key is disabled in v1 (rendered as an empty placeholder at 20% opacity).
 * Each key is ≥ 80×56px on mobile, ≥ 80×64px on kiosk (UI-SPEC tap targets).
 *
 * Props:
 *   onDigit(d)    — called with the string digit ("0"–"9") when a digit key taps
 *   onBackspace() — called when the backspace key taps
 *   disabled      — when true, all keys are inert (used during PIN submission)
 */

import './admin.css'

interface NumericKeypadProps {
  onDigit: (digit: string) => void
  onBackspace: () => void
  disabled?: boolean
}

const ROWS = [
  ['1', '2', '3'],
  ['4', '5', '6'],
  ['7', '8', '9'],
  ['*', '0', 'back'],
]

export function NumericKeypad({ onDigit, onBackspace, disabled = false }: NumericKeypadProps) {
  return (
    <div className="keypad" role="group" aria-label="Numeric keypad">
      {ROWS.map((row, ri) => (
        <div key={ri} className="keypad-row">
          {row.map((key) => {
            if (key === '*') {
              return (
                <button
                  key="star"
                  type="button"
                  className="keypad-key keypad-key--placeholder"
                  disabled
                  aria-hidden="true"
                  tabIndex={-1}
                >
                  {/* Not used in v1 */}
                </button>
              )
            }

            if (key === 'back') {
              return (
                <button
                  key="back"
                  type="button"
                  className="keypad-key keypad-key--action"
                  onClick={onBackspace}
                  disabled={disabled}
                  aria-label="Delete digit"
                >
                  {/* Backspace icon — inline SVG so no extra icon dep is needed */}
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                    focusable="false"
                  >
                    <path d="M21 4H8l-7 8 7 8h13a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2z" />
                    <line x1="18" y1="9" x2="12" y2="15" />
                    <line x1="12" y1="9" x2="18" y2="15" />
                  </svg>
                </button>
              )
            }

            return (
              <button
                key={key}
                type="button"
                className="keypad-key"
                onClick={() => onDigit(key)}
                disabled={disabled}
                aria-label={key}
              >
                {key}
              </button>
            )
          })}
        </div>
      ))}
    </div>
  )
}

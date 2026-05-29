/**
 * PairView — /pair route stub.
 *
 * STUB: This is a minimal placeholder so PairView.test.tsx can import and
 * render the component while PairView.test.tsx tests run RED on assertions.
 *
 * Plan 03-04 replaces this stub with the real implementation:
 *   - POST /api/devices/pairing-codes fetch on mount (issues fingerprint cookie)
 *   - M:SS countdown display (DM Mono, large, centered)
 *   - Auto-reroll on expiry (re-POST /api/devices/pairing-codes on 0:00)
 *   - GET /api/devices/me polling every 3s → navigate('/') on state=paired
 *   - Nordic Grid design tokens (pair.css)
 */

export function PairView() {
  return <div data-testid="pair-view" />
}

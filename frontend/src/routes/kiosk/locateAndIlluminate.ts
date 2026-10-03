/**
 * locateAndIlluminate — the single locate-and-light sequence every "select a
 * release" surface must run (gruvax-5zu).
 *
 * Extracted from ResultsList's row-tap / auto-select-top handlers so
 * RecentlyPulledStrip's chip tap performs the SAME sequence instead of just
 * writing selectedReleaseId to the store and stopping — the bug this fixes:
 * setSelectedReleaseId alone is bookkeeping for the SSE re-locate path
 * (KioskView.relocateActiveSelection), never a trigger. Every real "select"
 * path must pair it with an explicit /api/locate call.
 *
 * Fires /api/locate for the release, updates the store's locate result (which
 * drives the cube highlight), then fire-and-forgets /api/illuminate (D-01 —
 * illuminate never blocks the locate path; a degraded MQTT broker must not
 * prevent the cube from lighting on-screen).
 */

import { illuminateRecord, locateRelease } from '../../api/client'
import { useSessionStore } from '../../state/sessionStore'
import { useGruvaxStore } from '../../state/store'

export function locateAndIlluminate(releaseId: number, { illuminate = true } = {}): void {
  const token = useGruvaxStore.getState().invalidateLocateRequests()
  // D2-04: locate's profile_id query param is required — read at call-time via
  // getState() to stay stale-closure-safe (matches the prior inline callers).
  const { boundProfileId: profileId, profileBindingVersion } = useSessionStore.getState()
  const isCurrent = () => {
    const state = useGruvaxStore.getState()
    return (
      state.locateRequestToken === token &&
      state.selectedReleaseId === releaseId &&
      useSessionStore.getState().boundProfileId === profileId &&
      useSessionStore.getState().profileBindingVersion === profileBindingVersion
    )
  }
  void locateRelease(releaseId, profileId ?? undefined)
    .then((located) => {
      if (!isCurrent()) return
      useGruvaxStore.getState().setLocateResult(located)
      // Fire-and-forget illuminate — never block locate path (D-01)
      if (illuminate) {
        void illuminateRecord(located, profileId ?? undefined).catch(() => {
          // Swallow — broker may be in degraded mode
        })
      }
    })
    .catch(() => {
      // A failed background resync keeps the last known highlight; selection
      // failures clear it. Both paths consume the rejection and reject stale writes.
      if (illuminate && isCurrent()) useGruvaxStore.getState().setHighlightCube(null)
    })
}

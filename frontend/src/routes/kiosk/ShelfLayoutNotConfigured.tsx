/**
 * ShelfLayoutNotConfigured — zero-boundary profile affordance (Plan 09 / D-12).
 *
 * Shown in the KioskView shelf area when a search result IS in the bound
 * profile's collection (HTTP 200 from /api/locate) but resolves to no cube
 * (primary_cube: null, confidence: 0.0) because the profile has zero
 * cube boundaries configured.
 *
 * Distinct from:
 *   - EmptyCollectionState (bound-but-unsynced: no records at all)
 *   - NoResultsRow (search returned no matches)
 *   - A cleared/empty search box (shelfLayoutUnavailable is false in that state)
 *
 * Copy per UI-SPEC copywriting contract (sentence case, plain language):
 *   Heading: "Shelf layout not set up yet"
 *   Body: "This collection's records are loaded, but the shelf positions
 *          haven't been mapped yet. Ask the owner to set up the shelf layout
 *          for this collection in the admin screen."
 *
 * Design tokens only — no hardcoded hex.
 * Mirrors EmptyCollectionState structure: __heading + __body class convention.
 */

export function ShelfLayoutNotConfigured() {
  return (
    <div className="shelf-layout-unconfigured">
      <p className="shelf-layout-unconfigured__heading">Shelf layout not set up yet</p>
      <p className="shelf-layout-unconfigured__body">
        This collection's records are loaded, but the shelf positions haven't been mapped
        yet. Ask the owner to set up the shelf layout for this collection in the admin
        screen.
      </p>
    </div>
  )
}

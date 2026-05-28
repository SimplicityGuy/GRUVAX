/**
 * EmptyCollectionState — bound-but-unsynced profile affordance (Surface 7, D2-03).
 *
 * Shown in the KioskView results area when the bound profile has no synced records.
 * Distinct from NoResultsRow (which is "search returned no matches").
 *
 * Copy per UI-SPEC §Copywriting Contract:
 *   Heading: "No records yet" (sentence case, Space Grotesk 18px — NOT all-caps)
 *   Body: "This collection is syncing. Come back in a few minutes once sync completes."
 *
 * Design tokens only — no hardcoded hex.
 */

export function EmptyCollectionState() {
  return (
    <div className="empty-collection-state">
      <p className="empty-collection-state__heading">No records yet</p>
      <p className="empty-collection-state__body">
        This collection is syncing. Come back in a few minutes once sync completes.
      </p>
    </div>
  )
}

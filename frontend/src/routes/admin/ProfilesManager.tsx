/**
 * ProfilesManager — admin list of profiles at /admin/profiles.
 *
 * Shows a vertically-stacked profile card list + "ADD PROFILE" dashed row.
 * Tapping a card or the add row opens the ProfileDrawer bottom sheet.
 *
 * Empty state: "NO PROFILES" heading + "Add a profile to get started." (UI-SPEC §Empty State).
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 */

import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getAdminProfiles } from '../../api/adminClient'
import type { AdminProfile } from '../../api/types'
import { ProfileCard } from './ProfileCard'
import { ProfileDrawer } from './ProfileDrawer'
import { SyncToast } from '../../components/SyncToast'

type DrawerTarget = AdminProfile | 'new' | null

export function ProfilesManager() {
  const queryClient = useQueryClient()
  const [drawerTarget, setDrawerTarget] = useState<DrawerTarget>(null)
  const [syncToast, setSyncToast] = useState<{ message: string } | null>(null)

  const { data: profiles, isLoading, isError } = useQuery({
    queryKey: ['admin', 'profiles'],
    queryFn: getAdminProfiles,
    staleTime: 30_000,
  })

  function handleCardClick(profile: AdminProfile) {
    setDrawerTarget(profile)
  }

  function handleAddClick() {
    setDrawerTarget('new')
  }

  function handleDrawerClose() {
    setDrawerTarget(null)
  }

  function handleSyncComplete(message: string) {
    setSyncToast({ message })
    void queryClient.invalidateQueries({ queryKey: ['admin', 'profiles'] })
  }

  if (isLoading) {
    return (
      <div className="profiles-manager-loading" aria-live="polite">
        Loading profiles…
      </div>
    )
  }

  if (isError) {
    return (
      <div className="profiles-manager-error" role="alert">
        Failed to load profiles. Please try again.
      </div>
    )
  }

  const profileList = profiles ?? []

  return (
    <div className="profiles-manager">
      <h1 className="profiles-manager-heading">PROFILES</h1>

      {profileList.length === 0 ? (
        <div className="profiles-empty-state">
          <p className="profiles-empty-heading">NO PROFILES</p>
          <p className="profiles-empty-body">Add a profile to get started.</p>
        </div>
      ) : (
        <ul className="profiles-list" aria-label="Profile list">
          {profileList.map((profile, index) => (
            <li key={profile.id} className="profiles-list-item">
              <ProfileCard
                profile={profile}
                onClick={() => handleCardClick(profile)}
                index={index}
              />
            </li>
          ))}
        </ul>
      )}

      <button
        type="button"
        className="profiles-add-row"
        onClick={handleAddClick}
        aria-label="Add a new profile"
      >
        + ADD PROFILE
      </button>

      {drawerTarget !== null && (
        <ProfileDrawer
          target={drawerTarget}
          onClose={handleDrawerClose}
          onSyncComplete={handleSyncComplete}
        />
      )}

      {syncToast && (
        <SyncToast
          message={syncToast.message}
          onDismiss={() => setSyncToast(null)}
        />
      )}
    </div>
  )
}

/**
 * ProfileDrawer — bottom-sheet for all profile actions.
 *
 * Reuses the RecordPickerSheet markup verbatim:
 *   sheet-scrim + record-picker-sheet + sheet-drag-pill + sheet-body +
 *   sheet-heading + sheet-error + sheet-actions + focus trap (sheetRef).
 *
 * Action sections (contextual — show only what's applicable per UI-SPEC §Surface 2):
 *   - New profile: name input + create + connect flow
 *   - PENDING: PAT input (type=password + Eye/EyeOff) + CONNECT PAT CTA
 *   - CONNECTED: SYNC NOW, ROTATE PAT, RENAME, DELETE PROFILE
 *
 * Connect flow (D2-12): CONNECTING… spinner → on success transitions to SYNCING
 * and starts polling via TanStack Query refetchInterval.
 *
 * 202+poll (D2-13): GET /api/admin/profiles/{id} polled every 2s while in_progress.
 * On 'ok' → SyncProgressSection → success message + onSyncComplete callback.
 * On 'failed' → inline .sheet-error.
 *
 * Delete: modal confirm with item count, no device count (UI-SPEC §Destructive).
 * Default profile (DEFAULT_PROFILE_UUID) cannot be deleted.
 *
 * Error copy: all messages mapped to UI-SPEC friendly strings; no raw HTTP codes.
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Eye, EyeOff, Loader2 } from 'lucide-react'
import {
  connectAdminProfilePat,
  createAdminProfile,
  deleteAdminProfile,
  getAdminProfile,
  ProfileApiError,
  renameAdminProfile,
  rotateAdminProfilePat,
  syncAdminProfile,
} from '../../api/adminClient'
import type { AdminProfile } from '../../api/types'
import { SyncProgressSection } from './SyncProgressSection'

// The Default profile UUID — matches backend DEFAULT_PROFILE_UUID
const DEFAULT_PROFILE_UUID = '00000000-0000-0000-0000-000000000001'

/** Map backend error type discriminators to UI-SPEC friendly copy. */
function mapConnectError(err: unknown): string {
  if (err instanceof ProfileApiError) {
    switch (err.errorType) {
      case 'pat_rejected':
        return "This token was not accepted. Check that it's valid and has collection access, then try again."
      case 'user_id_collision':
        return 'This token belongs to someone who already has a profile. Each person needs their own token.'
      case 'user_id_mismatch':
        return 'This token belongs to a different account. Rotation requires a token from the same account.'
      case 'rate_limited_upstream':
      case 'upstream_unavailable':
        return 'Could not reach the music service. Check the connection and try again.'
      default:
        return 'Something went wrong. Try again in a moment.'
    }
  }
  if (err instanceof TypeError) {
    return 'Could not reach the music service. Check the connection and try again.'
  }
  return 'Something went wrong. Try again in a moment.'
}

export interface ProfileDrawerProps {
  target: AdminProfile | 'new'
  onClose: () => void
  onSyncComplete: (message: string) => void
}

type ConnectState = 'idle' | 'connecting' | 'syncing'
type DrawerMode = 'view' | 'rename' | 'rotate' | 'delete-confirm'

export function ProfileDrawer({ target, onClose, onSyncComplete }: ProfileDrawerProps) {
  const queryClient = useQueryClient()
  const sheetRef = useRef<HTMLDivElement>(null)
  const headingId = 'profile-drawer-heading'

  const isNew = target === 'new'
  const initialProfile = isNew ? null : target

  // Form state
  const [nameValue, setNameValue] = useState(initialProfile?.display_name ?? '')
  const [patValue, setPatValue] = useState('')
  const [showPat, setShowPat] = useState(false)

  // UI state
  const [connectState, setConnectState] = useState<ConnectState>('idle')
  const [drawerMode, setDrawerMode] = useState<DrawerMode>('view')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [profileId, setProfileId] = useState<string | null>(initialProfile?.id ?? null)
  const [isSaving, setIsSaving] = useState(false)
  const [syncSuccess, setSyncSuccess] = useState(false)

  // Focus trap: focus first focusable element on mount
  useEffect(() => {
    const el = sheetRef.current
    if (!el) return
    const focusable = el.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    )
    if (focusable.length > 0) focusable[0].focus()
  }, [])

  // Stable callback for sync completion — avoids stale closure in useQuery select
  const handleSyncCompleteStable = useCallback(
    (count: number | null) => {
      const countText = count != null ? count.toLocaleString('en-US') : '0'
      onSyncComplete(`Sync complete — ${countText} records`)
      void queryClient.invalidateQueries({ queryKey: ['admin', 'profiles'] })
    },
    [onSyncComplete, queryClient],
  )

  // 202+poll: poll GET /api/admin/profiles/{id} until a TERMINAL status is observed (D2-13)
  // refetchInterval pattern per RESEARCH §Pattern 4
  //
  // Fix (02-08): the old condition (`=== 'in_progress' ? 2000 : false`) halted polling on
  // ANY non-'in_progress' value, including transient null ticks that can appear between the
  // early 'in_progress' write (trigger_sync) and the atomic terminal write (_swap_inside_tx).
  // The corrected condition keeps polling until a TERMINAL status ('ok' | 'failed') is
  // observed, passing through 'in_progress', null, and any other non-terminal value.
  const { data: polledProfile } = useQuery({
    queryKey: ['admin', 'profiles', profileId],
    queryFn: () => getAdminProfile(profileId!),
    enabled: profileId !== null && connectState === 'syncing',
    refetchInterval: (query) => {
      const status = query.state.data?.last_sync_status
      return status === 'ok' || status === 'failed' ? false : 2000
    },
  })

  // React to terminal sync states from the poll.
  // We use a ref to track the last-handled status so this effect only fires once
  // per terminal event, and only calls setState from a stable callback.
  const handledSyncStatusRef = useRef<string | null>(null)
  useEffect(() => {
    if (!polledProfile || connectState !== 'syncing') return
    const status = polledProfile.last_sync_status
    if (status === handledSyncStatusRef.current) return

    // Updating state from within an effect is intentional here: we're reacting to an
    // external system state change (server poll result via TanStack Query). This matches
    // the React docs pattern for syncing with external state. The ref guard prevents
    // repeated firing for the same terminal event.
    if (status === 'ok') {
      handledSyncStatusRef.current = 'ok'
      setConnectState('idle') // eslint-disable-line react-hooks/set-state-in-effect
      setSyncSuccess(true)
      handleSyncCompleteStable(polledProfile.last_sync_item_count)
    } else if (status === 'failed') {
      handledSyncStatusRef.current = 'failed'
      setConnectState('idle')
      setSaveError('Sync failed. Tap Sync Now to try again.')
    }
  }, [polledProfile, connectState, handleSyncCompleteStable])

  const currentProfile: AdminProfile | null =
    polledProfile ?? initialProfile

  const isDefault = currentProfile?.id === DEFAULT_PROFILE_UUID

  const heading = isNew
    ? 'ADD PROFILE'
    : (currentProfile?.display_name.toUpperCase() ?? '')

  // ── Connect PAT ────────────────────────────────────────────────────────────
  async function handleConnect(isRotate = false) {
    if (!profileId) return
    if (!patValue.trim()) {
      setSaveError('Paste your token first.')
      return
    }

    setSaveError(null)
    setConnectState('connecting')

    try {
      const fn = isRotate ? rotateAdminProfilePat : connectAdminProfilePat
      await fn(profileId, { pat: patValue.trim() })
      // On success: transition to SYNCING (connect endpoint already kicked full sync)
      handledSyncStatusRef.current = null // reset so next terminal state is handled
      setConnectState('syncing')
      setPatValue('')
    } catch (err) {
      setConnectState('idle')
      setSaveError(mapConnectError(err))
    }
  }

  // ── Create new profile ─────────────────────────────────────────────────────
  async function handleCreate() {
    if (!nameValue.trim()) {
      setSaveError('Enter a profile name first.')
      return
    }

    setSaveError(null)
    setIsSaving(true)

    try {
      const created = await createAdminProfile({ display_name: nameValue.trim() })
      setProfileId(created.id)
      void queryClient.invalidateQueries({ queryKey: ['admin', 'profiles'] })
    } catch (err) {
      if (err instanceof ProfileApiError && err.errorType === 'display_name_taken') {
        setSaveError('A profile with that name already exists.')
      } else {
        setSaveError('Something went wrong. Try again in a moment.')
      }
    } finally {
      setIsSaving(false)
    }
  }

  // ── Rename ─────────────────────────────────────────────────────────────────
  async function handleSaveName() {
    if (!profileId || !nameValue.trim()) return
    if (nameValue.trim() === currentProfile?.display_name) {
      setDrawerMode('view')
      return
    }

    setSaveError(null)
    setIsSaving(true)

    try {
      await renameAdminProfile(profileId, { display_name: nameValue.trim() })
      void queryClient.invalidateQueries({ queryKey: ['admin', 'profiles'] })
      setDrawerMode('view')
    } catch (err) {
      if (err instanceof ProfileApiError && err.errorType === 'display_name_taken') {
        setSaveError('A profile with that name already exists.')
      } else {
        setSaveError('Something went wrong. Try again in a moment.')
      }
    } finally {
      setIsSaving(false)
    }
  }

  // ── Sync Now ───────────────────────────────────────────────────────────────
  async function handleSyncNow() {
    if (!profileId) return

    setSaveError(null)
    setSyncSuccess(false)
    handledSyncStatusRef.current = null

    try {
      await syncAdminProfile(profileId)
      setConnectState('syncing')
    } catch {
      setSaveError('Could not trigger sync. Try again in a moment.')
    }
  }

  // ── Delete ─────────────────────────────────────────────────────────────────
  async function handleConfirmDelete() {
    if (!profileId) return

    setSaveError(null)
    setIsSaving(true)

    try {
      await deleteAdminProfile(profileId)
      void queryClient.invalidateQueries({ queryKey: ['admin', 'profiles'] })
      onClose()
    } catch {
      setSaveError('Something went wrong. Try again in a moment.')
    } finally {
      setIsSaving(false)
    }
  }

  const isSyncing = connectState === 'syncing'
  const isConnecting = connectState === 'connecting'
  const profileStatus = currentProfile?.status ?? 'pending'

  return (
    <>
      {/* Scrim */}
      <div
        className="sheet-scrim"
        aria-hidden="true"
        onClick={isSyncing ? undefined : onClose}
      />

      {/* Bottom sheet */}
      <div
        ref={sheetRef}
        className="record-picker-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby={headingId}
      >
        {/* Drag pill */}
        <div className="sheet-drag-pill" aria-hidden="true" />

        <div className="sheet-body">
          <h2 id={headingId} className="sheet-heading">
            {heading}
          </h2>

          {/* ── NEW PROFILE: name input ─────────────────────────────────────── */}
          {isNew && profileId === null && (
            <div className="profile-drawer-section">
              <label
                htmlFor="profile-name-input"
                className="profile-field-label"
              >
                PROFILE NAME
              </label>
              <input
                id="profile-name-input"
                type="text"
                className="profile-field-input"
                value={nameValue}
                onChange={(e) => setNameValue(e.target.value)}
                placeholder="Profile name"
                maxLength={64}
                autoComplete="off"
                disabled={isSaving}
              />
            </div>
          )}

          {/* ── PENDING or ROTATE: PAT input ──────────────────────────────── */}
          {profileId !== null &&
            (profileStatus === 'pending' || drawerMode === 'rotate') &&
            !isSyncing &&
            !syncSuccess && (
            <div className="profile-drawer-section">
              <label
                htmlFor="profile-pat-input"
                className="profile-field-label"
              >
                PERSONAL ACCESS TOKEN
              </label>
              <div className="profile-pat-input-row">
                <input
                  id="profile-pat-input"
                  type={showPat ? 'text' : 'password'}
                  className="profile-field-input profile-field-input--pat"
                  value={patValue}
                  onChange={(e) => setPatValue(e.target.value)}
                  placeholder="Paste your discogsography PAT"
                  disabled={isConnecting}
                  autoComplete="off"
                />
                <button
                  type="button"
                  className="profile-pat-toggle"
                  onClick={() => setShowPat((v) => !v)}
                  aria-label={showPat ? 'Hide token' : 'Show token'}
                >
                  {showPat
                    ? <EyeOff size={16} aria-hidden="true" />
                    : <Eye size={16} aria-hidden="true" />
                  }
                </button>
              </div>
              <p className="profile-pat-instruction">
                {drawerMode === 'rotate'
                  ? 'Paste your new token below. It must belong to the same account.'
                  : 'Your token is encrypted and stored securely. It is never shown again after connecting.'
                }
              </p>
            </div>
          )}

          {/* ── SYNCING progress ──────────────────────────────────────────── */}
          {isSyncing && (
            <SyncProgressSection
              itemCount={polledProfile?.last_sync_item_count}
            />
          )}

          {/* ── Sync success inline message ────────────────────────────────── */}
          {syncSuccess && !isSyncing && polledProfile && (
            <p className="profile-sync-success">
              Sync complete — {(polledProfile.last_sync_item_count ?? 0).toLocaleString('en-US')} records
            </p>
          )}

          {/* ── RENAME: name input ─────────────────────────────────────────── */}
          {drawerMode === 'rename' && (
            <div className="profile-drawer-section">
              <label
                htmlFor="profile-rename-input"
                className="profile-field-label"
              >
                PROFILE NAME
              </label>
              <input
                id="profile-rename-input"
                type="text"
                className="profile-field-input"
                value={nameValue}
                onChange={(e) => setNameValue(e.target.value)}
                placeholder={currentProfile?.display_name ?? ''}
                maxLength={64}
                disabled={isSaving}
              />
            </div>
          )}

          {/* ── DELETE CONFIRM modal inline ────────────────────────────────── */}
          {drawerMode === 'delete-confirm' && currentProfile && (
            <div
              className="profile-delete-confirm"
              role="alertdialog"
              aria-labelledby="delete-confirm-heading"
            >
              <h3
                id="delete-confirm-heading"
                className="profile-delete-confirm-heading"
              >
                Delete this profile?
              </h3>
              <p className="profile-delete-confirm-body">
                This will permanently remove {currentProfile.display_name} and its{' '}
                <span className="profile-delete-item-count">
                  {(currentProfile.last_sync_item_count ?? 0).toLocaleString('en-US')} records
                </span>.{' '}
                This cannot be undone.
              </p>
            </div>
          )}

          {/* ── Error message ─────────────────────────────────────────────── */}
          {saveError && (
            <p className="sheet-error" role="alert">
              {saveError}
            </p>
          )}

          {/* ── Actions ───────────────────────────────────────────────────── */}
          <div className="sheet-actions">

            {/* NEW: create button (before profile exists) */}
            {isNew && profileId === null && (
              <button
                type="button"
                className="editor-btn-primary profile-btn-primary"
                onClick={() => void handleCreate()}
                disabled={isSaving || !nameValue.trim()}
                aria-busy={isSaving}
              >
                {isSaving ? 'CREATING…' : 'CREATE PROFILE'}
              </button>
            )}

            {/* PENDING: CONNECT PAT */}
            {profileId !== null &&
              profileStatus === 'pending' &&
              drawerMode !== 'rotate' &&
              !isSyncing &&
              !syncSuccess && (
              <button
                type="button"
                className="profile-btn-cta"
                onClick={() => void handleConnect(false)}
                disabled={isConnecting || !patValue.trim()}
                aria-busy={isConnecting}
              >
                {isConnecting
                  ? (
                    <>
                      <Loader2 size={16} className="profile-btn-spinner" aria-hidden="true" />
                      CONNECTING…
                    </>
                  )
                  : 'CONNECT PAT'
                }
              </button>
            )}

            {/* CONNECTED: SYNC NOW */}
            {profileStatus === 'connected' &&
              drawerMode === 'view' &&
              !isSyncing &&
              !syncSuccess && (
              <button
                type="button"
                className="profile-btn-secondary"
                onClick={() => void handleSyncNow()}
              >
                SYNC NOW
              </button>
            )}

            {/* CONNECTED: ROTATE PAT */}
            {profileStatus === 'connected' &&
              drawerMode === 'view' &&
              !isSyncing && (
              <button
                type="button"
                className="profile-btn-secondary"
                onClick={() => {
                  setDrawerMode('rotate')
                  setSaveError(null)
                  setPatValue('')
                }}
              >
                ROTATE PAT
              </button>
            )}

            {/* ROTATE PAT: submit */}
            {drawerMode === 'rotate' && !isSyncing && (
              <button
                type="button"
                className="profile-btn-cta"
                onClick={() => void handleConnect(true)}
                disabled={isConnecting || !patValue.trim()}
                aria-busy={isConnecting}
              >
                {isConnecting
                  ? (
                    <>
                      <Loader2 size={16} className="profile-btn-spinner" aria-hidden="true" />
                      CONNECTING…
                    </>
                  )
                  : 'ROTATE PAT'
                }
              </button>
            )}

            {/* RENAME: trigger */}
            {profileId !== null &&
              profileStatus !== 'pending' &&
              drawerMode === 'view' && (
              <button
                type="button"
                className="profile-btn-tertiary"
                onClick={() => {
                  setNameValue(currentProfile?.display_name ?? '')
                  setDrawerMode('rename')
                  setSaveError(null)
                }}
              >
                RENAME
              </button>
            )}

            {/* RENAME: SAVE NAME */}
            {drawerMode === 'rename' && (
              <button
                type="button"
                className="profile-btn-cta"
                onClick={() => void handleSaveName()}
                disabled={isSaving || !nameValue.trim()}
                aria-busy={isSaving}
              >
                {isSaving ? 'SAVING…' : 'SAVE NAME'}
              </button>
            )}

            {/* DELETE PROFILE: trigger */}
            {profileId !== null &&
              !isDefault &&
              drawerMode === 'view' &&
              !isSyncing && (
              <button
                type="button"
                className="profile-btn-destructive"
                onClick={() => setDrawerMode('delete-confirm')}
              >
                DELETE PROFILE
              </button>
            )}

            {/* DELETE CONFIRM: DELETE PROFILE */}
            {drawerMode === 'delete-confirm' && (
              <button
                type="button"
                className="profile-btn-destructive"
                onClick={() => void handleConfirmDelete()}
                disabled={isSaving}
                aria-busy={isSaving}
              >
                {isSaving ? 'DELETING…' : 'DELETE PROFILE'}
              </button>
            )}

            {/* DELETE CONFIRM: KEEP PROFILE */}
            {drawerMode === 'delete-confirm' && (
              <button
                type="button"
                className="sheet-cancel-btn"
                onClick={() => setDrawerMode('view')}
                disabled={isSaving}
              >
                KEEP PROFILE
              </button>
            )}

            {/* CLOSE — always present (never "Cancel" per UI-SPEC) */}
            {drawerMode !== 'delete-confirm' && (
              <button
                type="button"
                className="sheet-cancel-btn"
                onClick={
                  drawerMode === 'rename' || drawerMode === 'rotate'
                    ? () => { setDrawerMode('view'); setSaveError(null) }
                    : onClose
                }
              >
                CLOSE
              </button>
            )}
          </div>
        </div>
      </div>
    </>
  )
}

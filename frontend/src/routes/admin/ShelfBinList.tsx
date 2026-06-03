/**
 * ShelfBinList — bin-card list for one shelf unit (faithful port of sketch 002 Variant A).
 *
 * Route: /admin/cubes/:unit
 * Nav flow: CUBES → ShelfBinList → tap "✎ EDIT SEGMENTS" → BinWidthEditor
 *
 * Screen structure (mirrors sketch 002 Variant A exactly):
 *   - Back nav ("← CUBES") + title "EDIT SHELF A"
 *   - Locator header: mini 4×4 Kallax + "SHELF A"
 *   - Vertical list: CONFIGURED bins ONLY (non-empty cubes for this unit)
 *   - Dashed "＋ insert cut" dividers between bins (and before first / after last)
 *   - Each bin card: bin-number chip B{n}, "STARTS AT {label} · {record}", mini read-only strip, ✎ EDIT SEGMENTS
 *   - Insert opens RecordPickerSheet; the committed bin settles in from yellow → normal
 *
 * Insert-cut refresh (no manual reload):
 *   insertCut persists synchronously server-side (POST /cubes/insert-cut cascades
 *   cut points right by one in a single change-set). On commit we refetch
 *   ['admin','cubes'] + this unit's segments, then diff configured-bin keys to find
 *   the bin the cascade created (a formerly-empty cube turned non-empty) and play a
 *   ~3s settle animation (yellow = changed, per Nordic Grid).
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 * No innerHTML — all DOM built with React JSX.
 */

import { useState, useMemo, useRef, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { LocatorHeader } from './LocatorHeader'
import { SegmentStrip } from './SegmentStrip'
import { RecordPickerSheet } from './RecordPickerSheet'
import { adminGetCubes, getUnitSegments } from '../../api/adminClient'
import { shelfName, shelfLetter } from '../../lib/shelf'
import { useSessionStore } from '../../state/sessionStore'
import type { AdminCube, AdminCubesResponse } from '../../api/types'
import type { Segment } from '../../api/cubeTypes'

// ── useAdminCubesInvalidation ─────────────────────────────────────────────────
//
// Subscribes to the per-profile SSE channel (/api/events/{profileId}) while
// ShelfBinList is mounted, and invalidates the ['admin','cubes'] query on
// BOTH collection_changed (record counts changed) and boundary_changed (cube
// boundaries moved — fill data changes). This delivers UX-01 SC2: live fill
// reshading without a page reload.
//
// D-04: invalidate on both events (not just one).
// D-08 separation: admin-key invalidation lives here, NOT in KioskView.tsx.
//
// Key differences from KioskView's SSE consumer:
//   - Calls es.close() in useEffect cleanup: the admin listener is short-lived,
//     scoped to ShelfBinList mount/unmount. KioskView deliberately never closes
//     because it wants auto-reconnect; we do not.
//   - Uses .getState() (call-time, not reactive) to read boundProfileId, which
//     avoids stale-closure pitfall when the store updates after mount.
//
function useAdminCubesInvalidation(): void {
  const queryClient = useQueryClient()

  useEffect(() => {
    // Read boundProfileId at call time (Pitfall 4 stale-closure avoidance).
    // Matches KioskView.tsx:326 pattern.
    const profileId = useSessionStore.getState().boundProfileId
    if (!profileId) return

    const es = new EventSource(`/api/events/${profileId}`)

    es.addEventListener('collection_changed', () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'cubes'] })
    })

    es.addEventListener('boundary_changed', () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'cubes'] })
    })

    // WARNING-2 (v2.1 milestone audit): server (re)started → refresh fill shading so
    // admin ShelfBinList does not show stale per-cube occupancy after a server restart.
    es.addEventListener('server_hello', () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'cubes'] })
    })

    // UNLIKE KioskView, the admin listener is intentionally short-lived —
    // close on unmount to prevent accumulating connections across admin navigation
    // (T-10-05 mitigation).
    return () => es.close()
  }, [queryClient])
}

const ROWS = 4
const COLS = 4

/** How long the newly-committed bin glows yellow before settling to normal. */
const CHANGE_ANIM_MS = 3000

/** Stable display bin number (1-based, row-major). */
function binNum(cube: AdminCube): number {
  return cube.row * COLS + cube.col + 1
}

/** Stable per-cube key within a unit. */
function cubeKey(cube: AdminCube): string {
  return `${cube.row}-${cube.col}`
}

interface InsertState {
  /** The cube after which we're inserting (null = before first bin). */
  afterCube: AdminCube | null
  /** After-bin display number. */
  afterDisplay: number
}

export function ShelfBinList() {
  const { unit } = useParams<{ unit: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const unitId = Number(unit)

  // D-04: invalidate ['admin','cubes'] when collection or boundaries change externally.
  // Admin SSE listener opens on mount, closes on unmount (no leaked EventSource).
  useAdminCubesInvalidation()

  // ── Sheet state ──────────────────────────────────────────────────────────────
  const [insertState, setInsertState] = useState<InsertState | null>(null)
  const [editingCube, setEditingCube] = useState<AdminCube | null>(null)

  // Cube keys ("row-col") to play the settle animation on after a commit.
  const [recentlyChanged, setRecentlyChanged] = useState<Set<string>>(new Set())
  const changeTimerRef = useRef<number | null>(null)

  // Clear any pending settle timer on unmount.
  useEffect(() => {
    return () => {
      if (changeTimerRef.current !== null) window.clearTimeout(changeTimerRef.current)
    }
  }, [])

  // ── Data ─────────────────────────────────────────────────────────────────────
  const { data: cubesData, isLoading, isError } = useQuery({
    queryKey: ['admin', 'cubes'],
    queryFn: adminGetCubes,
    staleTime: 60_000,
  })

  const configuredBins = useMemo(() => {
    if (!cubesData) return []
    return cubesData.cubes
      .filter((c) => c.unit_id === unitId && !c.is_empty)
      .sort((a, b) => a.row !== b.row ? a.row - b.row : a.col - b.col)
  }, [cubesData, unitId])

  // ── Handlers ─────────────────────────────────────────────────────────────────
  function openInsertAfter(afterCube: AdminCube | null) {
    const afterDisplay = afterCube ? binNum(afterCube) : 0
    setInsertState({ afterCube, afterDisplay })
  }

  function openEditCut(cube: AdminCube) {
    setEditingCube(cube)
  }

  /** Flag freshly-appeared bins for the settle animation, auto-clearing after ~3s. */
  function flagChanged(keys: string[]) {
    if (keys.length === 0) return
    setRecentlyChanged(new Set(keys))
    if (changeTimerRef.current !== null) window.clearTimeout(changeTimerRef.current)
    changeTimerRef.current = window.setTimeout(() => {
      setRecentlyChanged(new Set())
      changeTimerRef.current = null
    }, CHANGE_ANIM_MS)
  }

  async function handleInsertCommit() {
    // Snapshot configured bins BEFORE the refetch so we can detect the bin the
    // cascade just created (a formerly-empty cube turning non-empty). insertCut
    // has already persisted server-side by the time onCommit fires.
    const beforeKeys = new Set(configuredBins.map(cubeKey))

    // Close the sheet immediately — no manual reload needed.
    setInsertState(null)

    // Await BOTH invalidations: the cubes refetch surfaces the new interactive
    // BinCard (so the diff sees it), and the segments refetch refreshes every
    // shifted bin's mini-strip — otherwise a settled bin could briefly show the
    // pre-cascade strip while the animation signals "this is now correct".
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['admin', 'cubes'] }),
      queryClient.invalidateQueries({ queryKey: ['admin', 'segments', unitId] }),
    ])

    const fresh = queryClient.getQueryData<AdminCubesResponse>(['admin', 'cubes'])
    if (!fresh) return
    const appeared = fresh.cubes
      .filter((c) => c.unit_id === unitId && !c.is_empty)
      .map((c) => `${c.row}-${c.col}`)
      .filter((key) => !beforeKeys.has(key))

    flagChanged(appeared)
  }

  async function handleEditCommit() {
    const target = editingCube
    setEditingCube(null)
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['admin', 'cubes'] }),
      queryClient.invalidateQueries({ queryKey: ['admin', 'segments', unitId] }),
    ])
    // The edited bin keeps its position; settle it so the change is visible.
    if (target) flagChanged([cubeKey(target)])
  }

  // ── Loading / error ──────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="cut-point-editor-loading" aria-live="polite">
        Loading…
      </div>
    )
  }

  if (isError || !cubesData) {
    return (
      <div className="cubes-grid-error" role="alert">
        Failed to load bins. Please try again.
      </div>
    )
  }

  const shelfLtr = shelfLetter(unitId)
  const shelfDisplayName = shelfName(unitId)
  const totalBins = ROWS * COLS
  const unconfiguredCount = totalBins - configuredBins.length

  return (
    <div className="sbl-screen">
      {/* Header — back + title */}
      <header className="sbl-header">
        <button
          type="button"
          className="sbl-back"
          onClick={() => void navigate('/admin/cubes')}
          aria-label="Back to shelves"
        >
          ← CUBES
        </button>
        <h1 className="sbl-title">EDIT SHELF {shelfLtr}</h1>
      </header>

      {/* Locator header — mini Kallax, no specific bin lit.
          cubes prop wires fill-shading data from the already-fetched query
          (Pitfall 5: without this, LocatorHeader has no fill data to render). */}
      <div className="sbl-locator">
        <LocatorHeader
          unitId={unitId}
          row={-1}
          col={-1}
          shelfName={shelfDisplayName}
          rows={ROWS}
          cols={COLS}
          cubes={cubesData?.cubes ?? []}
        />
      </div>

      {/* Bin-card list */}
      <div className="sbl-list">
        {/* Insert-cut divider BEFORE first bin */}
        {configuredBins.length > 0 && (
          <InsertCutDivider onTap={() => openInsertAfter(null)} />
        )}

        {configuredBins.map((cube) => {
          const display = binNum(cube)

          return (
            <div key={cubeKey(cube)}>
              <BinCard
                cube={cube}
                display={display}
                unitId={unitId}
                isChanged={recentlyChanged.has(cubeKey(cube))}
                onEditSegments={() =>
                  void navigate(`/admin/cubes/${unitId}/${cube.row}/${cube.col}`)
                }
                onEditCut={() => openEditCut(cube)}
              />

              {/* Insert-cut divider AFTER each bin */}
              <InsertCutDivider onTap={() => openInsertAfter(cube)} />
            </div>
          )
        })}

        {/* Empty-state */}
        {configuredBins.length === 0 && (
          <div className="sbl-empty">
            <p className="sbl-empty-text">No bins configured for this shelf yet.</p>
            <InsertCutDivider onTap={() => openInsertAfter(null)} />
          </div>
        )}

        {/* Unconfigured capacity hint */}
        {unconfiguredCount > 0 && configuredBins.length > 0 && (
          <p className="sbl-unconfigured-hint">
            {unconfiguredCount} of {totalBins} bins unconfigured
          </p>
        )}
      </div>

      {/* RecordPickerSheet — insert mode */}
      {insertState && (
        <RecordPickerSheet
          mode="insert"
          unitId={unitId}
          row={insertState.afterCube?.row ?? 0}
          col={insertState.afterCube?.col ?? 0}
          afterBinDisplay={insertState.afterDisplay}
          onCommit={() => void handleInsertCommit()}
          onCancel={() => setInsertState(null)}
        />
      )}

      {/* RecordPickerSheet — edit cut mode */}
      {editingCube && (
        <RecordPickerSheet
          mode="edit"
          unitId={unitId}
          row={editingCube.row}
          col={editingCube.col}
          onCommit={() => void handleEditCommit()}
          onCancel={() => setEditingCube(null)}
        />
      )}
    </div>
  )
}

/** ── BinCard — faithful port of sketch 002 Variant A bin card ─────────────── */
function BinCard({
  cube,
  display,
  unitId,
  isChanged,
  onEditSegments,
  onEditCut,
}: {
  cube: AdminCube
  display: number
  unitId: number
  isChanged: boolean
  onEditSegments: () => void
  onEditCut: () => void
}) {
  // Fetch segments for this bin's mini strip (only when visible — React Query caches)
  const { data: segsData } = useQuery({
    queryKey: ['admin', 'segments', unitId, cube.row, cube.col],
    queryFn: () => getUnitSegments(unitId, cube.row, cube.col),
    staleTime: 60_000,
  })

  const segments: Segment[] = segsData?.segments ?? []

  return (
    <div className={`sbl-bincard${isChanged ? ' sbl-bincard--changed' : ''}`}>
      <div className="sbl-bincard-top">
        {/* Square bin-number chip */}
        <div className="sbl-binno">{display}</div>

        {/* "STARTS AT label · record" */}
        <div className="sbl-cutinfo">
          <span className="sbl-cutinfo-k">STARTS AT</span>
          <div className="sbl-cutinfo-v">
            <span className="sbl-cutinfo-lab">{cube.first_label}</span>
            <span className="sbl-cutinfo-rec">{cube.first_catalog}</span>
          </div>
        </div>

        {/* Edit cut-point button */}
        <button
          type="button"
          className="sbl-editbtn"
          title="Edit cut point"
          onClick={onEditCut}
          aria-label={`Edit cut point for bin ${display}`}
        >
          ✎
        </button>
      </div>

      {/* Mini read-only segment strip */}
      <div className="sbl-ministrip-wrap">
        <SegmentStrip segments={segments} isReadOnly />
      </div>

      {/* Edit segments action */}
      <button
        type="button"
        className="sbl-edit-segments-btn"
        onClick={onEditSegments}
      >
        ✎ EDIT SEGMENTS
      </button>
    </div>
  )
}

/** ── InsertCutDivider — dashed "＋ insert cut" line between bins ─────────────── */
function InsertCutDivider({ onTap }: { onTap: () => void }) {
  return (
    <div className="sbl-insert">
      <div className="sbl-insert-line" />
      <button
        type="button"
        className="sbl-insert-btn"
        onClick={onTap}
        aria-label="Insert cut point"
      >
        ＋ insert cut
      </button>
      <div className="sbl-insert-line" />
    </div>
  )
}

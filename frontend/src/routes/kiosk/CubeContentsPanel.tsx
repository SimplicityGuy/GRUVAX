/**
 * CubeContentsPanel — bottom-sheet side panel for cube-tap reverse lookup (CUBE-09).
 *
 * Triggered by any cube tap on the public kiosk view. No admin auth required (D-15).
 * Fetches GET /api/cubes/{u}/{r}/{c} via TanStack Query and renders:
 *   - Cube address heading "CUBE B2"
 *   - Fill level row "94 RECORDS · 99% FULL"
 *   - First / last boundary records
 *   - ~7 evenly-sampled records
 *   - Empty-state copy (D-16)
 *   - D-16: "EDIT THIS CUBE" link-button when admin is logged in
 *
 * Dismiss: tap outside panel or drag handle area.
 *
 * UI-SPEC §H — bottom sheet design contract.
 * Design tokens only — no hardcoded hex values (CLAUDE.md constraint).
 */

import { useQuery } from '@tanstack/react-query'
import { fetchCubeContents } from '../../api/client'
import { useAdminStore } from '../../state/adminStore'
import type { CubeRef } from '../../api/types'

interface CubeContentsPanelProps {
  /** The cube that was tapped. null = panel closed. */
  cube: CubeRef | null
  /** Called to close the panel (tap outside / drag handle). */
  onDismiss: () => void
}

/**
 * Format a cube's address for display ("CUBE B2").
 * Row letters: A-H (Shelf A rows A-D, Shelf B rows E-H).
 */
function cubeAddress(unitId: number, row: number, col: number): string {
  const ROW_LETTERS = 'ABCDEFGH'
  const baseOffset = (unitId - 1) * 4
  const rowLetter = ROW_LETTERS[baseOffset + row] ?? '?'
  return `CUBE ${rowLetter}${col + 1}`
}

/**
 * Format fill level as a percentage string (e.g. "99%").
 * Caps display at 999% to avoid layout issues for wildly overstuffed cubes.
 */
function formatFillPct(fillLevel: number): string {
  return `${Math.min(Math.round(fillLevel * 100), 999)}%`
}

export function CubeContentsPanel({ cube, onDismiss }: CubeContentsPanelProps) {
  const isLoggedIn = useAdminStore((s) => s.isLoggedIn)

  const panelOpen = cube !== null

  const { data, isLoading, isError } = useQuery({
    queryKey: ['cube-contents', cube?.unit_id, cube?.row, cube?.col],
    queryFn: () => {
      if (!cube) throw new Error('No cube selected')
      return fetchCubeContents(cube.unit_id, cube.row, cube.col)
    },
    enabled: panelOpen,
    staleTime: 30_000,
  })

  if (!panelOpen) return null

  const address = cube ? cubeAddress(cube.unit_id, cube.row, cube.col) : ''

  // Determine empty-state copy (UI-SPEC §H Copywriting, D-16)
  const isEmpty = data?.is_empty ?? false
  const hasNoRecords = data ? data.total_count === 0 : false

  return (
    <>
      {/* Scrim — tap outside panel to dismiss */}
      <div
        className="cube-panel-scrim"
        onClick={onDismiss}
        aria-hidden="true"
      />

      {/* Bottom sheet panel */}
      <div
        className="cube-panel"
        role="dialog"
        aria-label={address}
        aria-modal="true"
      >
        {/* Drag handle */}
        <div className="cube-panel__handle" onClick={onDismiss} aria-label="Close panel" />

        <div className="cube-panel__content">
          {/* Heading */}
          <h2 className="cube-panel__heading">{address}</h2>

          {isLoading && (
            <p className="cube-panel__loading">Loading…</p>
          )}

          {isError && (
            <p className="cube-panel__error">Could not load cube contents. Try again.</p>
          )}

          {data && (
            <>
              {/* Empty state */}
              {isEmpty || hasNoRecords ? (
                <div className="cube-panel__empty">
                  {isEmpty ? (
                    <>
                      <p className="cube-panel__empty-heading">No records assigned to this cube yet.</p>
                      <p className="cube-panel__empty-body">This cube has no boundaries set.</p>
                    </>
                  ) : (
                    <>
                      <p className="cube-panel__empty-heading">Nothing in this cube</p>
                      <p className="cube-panel__empty-body">
                        Boundaries are set but no records from the collection fall in this range.
                        Check the boundary values.
                      </p>
                    </>
                  )}
                  {isLoggedIn && (
                    <a
                      href={`/admin/cubes/${cube.unit_id}/${cube.row}/${cube.col}`}
                      className="cube-panel__edit-link"
                    >
                      EDIT THIS CUBE
                    </a>
                  )}
                </div>
              ) : (
                <>
                  {/* Fill level row */}
                  <p className="cube-panel__fill-row">
                    {data.total_count} RECORDS · {formatFillPct(data.fill_level)} FULL
                  </p>

                  {/* Fill bar (same color rules as CUBE-07, UI-SPEC §H) */}
                  <div className="cube-panel__fill-bar-track">
                    <div
                      className="cube-panel__fill-bar"
                      style={{
                        width: `${Math.min(data.fill_level, 1.0) * 100}%`,
                        backgroundColor:
                          data.fill_level < 0.8
                            ? 'var(--gruvax-blue-light)'
                            : data.fill_level <= 1.0
                              ? 'var(--gruvax-yellow)'
                              : 'var(--gruvax-error)',
                      }}
                      aria-hidden="true"
                    />
                  </div>

                  {/* First / Last boundary records */}
                  {(data.first_label || data.first_catalog) && (
                    <div className="cube-panel__boundary-row">
                      <span className="cube-panel__boundary-label">FIRST</span>
                      <span className="cube-panel__boundary-value">
                        {data.first_label} {data.first_catalog}
                      </span>
                    </div>
                  )}
                  {(data.last_label || data.last_catalog) && (
                    <div className="cube-panel__boundary-row">
                      <span className="cube-panel__boundary-label">LAST</span>
                      <span className="cube-panel__boundary-value">
                        {data.last_label} {data.last_catalog}
                      </span>
                    </div>
                  )}

                  {/* ~7 sampled records */}
                  {data.sample_records.length > 0 && (
                    <ul className="cube-panel__sample-list" aria-label="Sample records">
                      {data.sample_records.map((r, i) => (
                        <li
                          key={r.release_id}
                          className={`cube-panel__sample-row${i % 2 === 0 ? '' : ' cube-panel__sample-row--alt'}`}
                        >
                          <span className="cube-panel__sample-catalog">{r.catalog_number}</span>
                          <span className="cube-panel__sample-label">{r.label}</span>
                        </li>
                      ))}
                    </ul>
                  )}

                  {/* D-16: admin shortcut — only when logged in */}
                  {isLoggedIn && (
                    <a
                      href={`/admin/cubes/${cube.unit_id}/${cube.row}/${cube.col}`}
                      className="cube-panel__edit-link"
                    >
                      EDIT THIS CUBE
                    </a>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </div>
    </>
  )
}

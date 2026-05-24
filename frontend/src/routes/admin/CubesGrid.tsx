/**
 * CubesGrid — admin entry point: lists SHELVES (Kallax units), not individual cubes.
 *
 * Tapping a shelf entry navigates to /admin/cubes/:unit (ShelfBinList).
 * Each shelf shows:
 *   - "SHELF A" display name (via shelf.ts shelfName())
 *   - Mini 4×4 Kallax preview (lit cells = configured bins)
 *   - Bin count: "{n} of 16 bins configured"
 *
 * No raw unit/row/col triples are shown — all addressing uses SHELF A / BIN n notation.
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 */

import { useMemo } from 'react'
import { useNavigate } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { adminGetCubes, downloadBoundariesYaml } from '../../api/adminClient'
import { shelfName } from '../../lib/shelf'
import type { AdminCube } from '../../api/types'

const ROWS = 4
const COLS = 4
const TOTAL_BINS = ROWS * COLS

interface ShelfSummary {
  unitId: number
  displayName: string
  configuredCount: number
  cubes: AdminCube[]
}

function groupByUnit(cubes: AdminCube[]): ShelfSummary[] {
  const map = new Map<number, AdminCube[]>()
  for (const cube of cubes) {
    const arr = map.get(cube.unit_id) ?? []
    arr.push(cube)
    map.set(cube.unit_id, arr)
  }
  return Array.from(map.entries())
    .sort(([a], [b]) => a - b)
    .map(([unitId, unitCubes]) => ({
      unitId,
      displayName: shelfName(unitId),
      configuredCount: unitCubes.filter((c) => !c.is_empty).length,
      cubes: unitCubes,
    }))
}

export function CubesGrid() {
  const navigate = useNavigate()

  const { data, isLoading, isError } = useQuery({
    queryKey: ['admin', 'cubes'],
    queryFn: adminGetCubes,
    staleTime: 60_000,
  })

  const shelves = useMemo(
    () => (data ? groupByUnit(data.cubes) : []),
    [data],
  )

  if (isLoading) {
    return (
      <div className="cubes-grid-loading" aria-live="polite">
        Loading shelves…
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="cubes-grid-error" role="alert">
        Failed to load shelves. Please try again.
      </div>
    )
  }

  return (
    <div className="shelves-list">
      {shelves.map((shelf) => (
        <button
          key={shelf.unitId}
          type="button"
          className="shelf-card"
          onClick={() => void navigate(`/admin/cubes/${shelf.unitId}`)}
          aria-label={`${shelf.displayName}: ${shelf.configuredCount} of ${TOTAL_BINS} bins configured`}
        >
          {/* Mini 4×4 Kallax preview */}
          <MiniKallax cubes={shelf.cubes} />

          {/* Shelf label + bin count */}
          <div className="shelf-card-info">
            <span className="shelf-card-name">{shelf.displayName}</span>
            <span className="shelf-card-count">
              {shelf.configuredCount} of {TOTAL_BINS} bins configured
            </span>
          </div>

          <span className="shelf-card-chevron" aria-hidden="true">{'›'}</span>
        </button>
      ))}

      {shelves.length === 0 && (
        <p className="shelves-empty">No shelves configured yet.</p>
      )}

      {/* EXPORT BOUNDARIES — secondary action row (UI-SPEC Surface 6, BAK-01) */}
      <div className="shelves-export-row">
        <button
          type="button"
          className="shelves-export-btn"
          onClick={() => { void downloadBoundariesYaml() }}
        >
          {/* Lucide Download icon */}
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="16" height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="7 10 12 15 17 10" />
            <line x1="12" y1="15" x2="12" y2="3" />
          </svg>
          EXPORT BOUNDARIES
        </button>
      </div>
    </div>
  )
}

/** Compact 4×4 Kallax preview — lit cells = configured (non-empty) bins. */
function MiniKallax({ cubes }: { cubes: AdminCube[] }) {
  const configuredKeys = useMemo(
    () => new Set(cubes.filter((c) => !c.is_empty).map((c) => `${c.row}-${c.col}`)),
    [cubes],
  )

  return (
    <div
      className="shelf-mini-kallax"
      aria-hidden="true"
    >
      {Array.from({ length: ROWS }, (_, r) =>
        Array.from({ length: COLS }, (_, c) => {
          const key = `${r}-${c}`
          return (
            <div
              key={key}
              className={`shelf-mini-cell${configuredKeys.has(key) ? ' shelf-mini-cell--lit' : ''}`}
            />
          )
        }),
      )}
    </div>
  )
}

/**
 * CubesGrid — admin view of all Kallax cubes with fill bars and A-Z rail.
 *
 * Fetches admin cube data via GET /api/admin/cubes.
 * Tapping a cube navigates to /admin/cubes/:unitId/:row/:col for editing.
 *
 * Grouped by unit_id. Within each unit, renders a grid of cube cards
 * showing label_first → label_last range, catalog range, and a FillBar.
 *
 * The AlphaRail on the right triggers smooth scroll to the first cube whose
 * label_first starts with the chosen letter.
 */

import { useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { adminGetCubes } from '../../api/adminClient'
import type { AdminCube } from '../../api/types'
import { AlphaRail } from './AlphaRail'
import { FillBar } from './FillBar'
import { shelfLetter } from '../../lib/shelf'

/** Group cubes by unit_id preserving original order within each unit. */
function groupByUnit(cubes: AdminCube[]): Map<number, AdminCube[]> {
  const map = new Map<number, AdminCube[]>()
  for (const cube of cubes) {
    const existing = map.get(cube.unit_id)
    if (existing) {
      existing.push(cube)
    } else {
      map.set(cube.unit_id, [cube])
    }
  }
  return map
}

export function CubesGrid() {
  const navigate = useNavigate()
  const containerRef = useRef<HTMLDivElement>(null)
  const [activeLetter, setActiveLetter] = useState<string | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['admin', 'cubes'],
    queryFn: adminGetCubes,
    staleTime: 60_000,
  })

  const cubesByUnit = useMemo(
    () => (data ? groupByUnit(data.cubes) : new Map<number, AdminCube[]>()),
    [data],
  )

  /** All unique first-letters (uppercase) of first_label across all cubes (CR-01). */
  const activeLetters = useMemo<Set<string>>(() => {
    if (!data) return new Set()
    const letters = new Set<string>()
    for (const cube of data.cubes) {
      if (cube.first_label) {
        const firstChar = cube.first_label.charAt(0).toUpperCase()
        if (/[A-Z]/.test(firstChar)) {
          letters.add(firstChar)
        }
      }
    }
    return letters
  }, [data])

  /** Scroll to first cube whose label_first starts with the given letter. */
  function handleLetterTap(letter: string) {
    if (!containerRef.current) return
    const target = containerRef.current.querySelector<HTMLElement>(
      `[data-label-letter="${letter}"]`,
    )
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' })
      setActiveLetter(letter)
    }
  }

  function handleCubeTap(cube: AdminCube) {
    void navigate(`/admin/cubes/${cube.unit_id}/${cube.row}/${cube.col}`)
  }

  if (isLoading) {
    return (
      <div className="cubes-grid-loading" aria-live="polite">
        Loading cubes...
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="cubes-grid-error" role="alert">
        Failed to load cubes. Please try again.
      </div>
    )
  }

  return (
    <div className="cubes-grid-outer">
      <div className="cubes-grid-scroll" ref={containerRef}>
        {Array.from(cubesByUnit.entries()).map(([unitId, cubes]) => (
          <section key={unitId} className="cubes-unit-section">
            <h2 className="cubes-unit-heading">SHELF {shelfLetter(unitId)}</h2>

            <div className="cubes-unit-grid">
              {cubes.map((cube) => {
                const letterAttr = cube.first_label
                  ? cube.first_label.charAt(0).toUpperCase()
                  : undefined
                const isAlphaAnchor =
                  letterAttr && activeLetters.has(letterAttr)
                    ? {
                        'data-label-letter': letterAttr,
                      }
                    : {}

                return (
                  <button
                    key={`${cube.unit_id}-${cube.row}-${cube.col}`}
                    type="button"
                    className={`cube-card${cube.is_empty ? ' cube-card--empty' : ''}`}
                    onClick={() => handleCubeTap(cube)}
                    aria-label={`Cube ${cube.unit_id}-${cube.row}-${cube.col}: ${cube.first_label} to ${cube.last_label}`}
                    {...isAlphaAnchor}
                  >
                    <div className="cube-card-header">
                      <span className="cube-card-ref">
                        {cube.unit_id}/{cube.row}/{cube.col}
                      </span>
                      {cube.is_empty && (
                        <span className="cube-card-empty-badge">EMPTY</span>
                      )}
                    </div>

                    <div className="cube-card-body">
                      <p className="cube-card-label">{cube.first_label}</p>
                      <p className="cube-card-catalog">{cube.first_catalog}</p>
                      {cube.last_label !== cube.first_label && (
                        <>
                          <p className="cube-card-label cube-card-label--last">
                            {cube.last_label}
                          </p>
                          <p className="cube-card-catalog">{cube.last_catalog}</p>
                        </>
                      )}
                    </div>

                    <FillBar fillLevel={cube.fill_level} heightPx={3} />
                  </button>
                )
              })}
            </div>
          </section>
        ))}
      </div>

      <AlphaRail activeLetters={activeLetters} onLetterTap={handleLetterTap} activeLetter={activeLetter} />
    </div>
  )
}

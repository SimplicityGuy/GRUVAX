/**
 * adminClient error-body flattening tests (gruvax-imeq).
 *
 * Bare FastAPI has no repo-wide exception handler, so ``HTTPException(detail={...})``
 * (used by the import endpoints' parse/format/size errors) serializes as NESTED
 * ``{"detail": {...}}`` while ``JSONResponse(content={...})`` (cubes.py's 400s)
 * is already flat. Before the fix, uploadImportBoundaries/uploadImportSettings read
 * ``.type`` / ``.message`` top-level only — both undefined for the nested shape —
 * so a parse error surfaced as an untyped, messageless BulkSaveError and the UI
 * (Import.tsx) rendered a blank error card.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { BulkSaveError, uploadImportBoundaries, uploadImportSettings } from './adminClient'

function makeFile(name: string, content = 'irrelevant'): File {
  return new File([content], name, { type: 'text/plain' })
}

beforeEach(() => {
  vi.unstubAllGlobals()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('uploadImportBoundaries — nested HTTPException(detail=...) error bodies', () => {
  it('surfaces type/message from a NESTED {"detail": {...}} 422 body (parse_error)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => (
      {
        ok: false,
        status: 422,
        json: async () => ({
          detail: {
            type: 'parse_error',
            message: "Missing or unsupported version field — YAML boundary documents must contain version: '1'",
          },
        }),
      } as Response
    )))

    const file = makeFile('boundaries.yaml')
    let caught: unknown
    try {
      await uploadImportBoundaries(file, null, true)
    } catch (err) {
      caught = err
    }

    expect(caught).toBeInstanceOf(BulkSaveError)
    const err = caught as BulkSaveError
    expect(err.status).toBe(422)
    expect(err.errorType).toBe('parse_error')
    expect(err.serverMessage).toBe(
      "Missing or unsupported version field — YAML boundary documents must contain version: '1'",
    )
    // .body must ALSO be flattened — downstream consumers (Import.tsx's
    // parseServerErrors) read body.type / body.message top-level directly.
    expect(err.body.type).toBe('parse_error')
    expect(err.body.message).toBe(
      "Missing or unsupported version field — YAML boundary documents must contain version: '1'",
    )
  })

  it('still handles an already-FLAT 400 body (cubes.py-style JSONResponse convention)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => (
      {
        ok: false,
        status: 400,
        json: async () => ({
          type: 'contiguity_violation',
          message: 'X would be split across non-adjacent bins.',
        }),
      } as Response
    )))

    const file = makeFile('boundaries.csv')
    let caught: unknown
    try {
      await uploadImportBoundaries(file, null, true)
    } catch (err) {
      caught = err
    }

    expect(caught).toBeInstanceOf(BulkSaveError)
    const err = caught as BulkSaveError
    expect(err.errorType).toBe('contiguity_violation')
    expect(err.serverMessage).toBe('X would be split across non-adjacent bins.')
  })
})

describe('uploadImportSettings — nested HTTPException(detail=...) error bodies', () => {
  it('surfaces type/message from a NESTED {"detail": {...}} 422 body', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => (
      {
        ok: false,
        status: 422,
        json: async () => ({
          detail: { type: 'parse_error', message: 'Settings YAML must be a mapping' },
        }),
      } as Response
    )))

    const file = makeFile('settings.yaml')
    let caught: unknown
    try {
      await uploadImportSettings(file)
    } catch (err) {
      caught = err
    }

    expect(caught).toBeInstanceOf(BulkSaveError)
    const err = caught as BulkSaveError
    expect(err.errorType).toBe('parse_error')
    expect(err.serverMessage).toBe('Settings YAML must be a mapping')
  })
})

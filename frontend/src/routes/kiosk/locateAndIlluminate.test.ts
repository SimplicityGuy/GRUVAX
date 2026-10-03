import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { LocateResult } from '../../api/types'
import { useGruvaxStore } from '../../state/store'
import { useSessionStore } from '../../state/sessionStore'
import { locateAndIlluminate } from './locateAndIlluminate'

vi.mock('../../api/client', () => ({
  locateRelease: vi.fn(),
  illuminateRecord: vi.fn().mockResolvedValue(undefined),
}))
import { illuminateRecord, locateRelease } from '../../api/client'

function deferred() {
  let resolve!: (result: LocateResult) => void
  let reject!: (error: Error) => void
  const promise = new Promise<LocateResult>((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}

function located(releaseId: number): LocateResult {
  return {
    release_id: releaseId,
    primary_cube: { unit_id: 1, row: 0, col: releaseId },
    label_span: [],
    sub_cube_interval: null,
    confidence: 0.8,
    generated_at: '2026-10-03T00:00:00Z',
    estimator_version: 'test',
  }
}

function select(releaseId: number) {
  useGruvaxStore.getState().setSelectedReleaseId(releaseId)
  locateAndIlluminate(releaseId)
}

async function settle() {
  await Promise.resolve()
  await Promise.resolve()
}

beforeEach(() => {
  vi.clearAllMocks()
  useGruvaxStore.getState().clearSearch()
  useGruvaxStore.getState().setQuery('record')
  useSessionStore.setState({ boundProfileId: 'profile-a' })
})

describe('shared locate generation', () => {
  it('keeps the selected record locate pending while typing before new results arrive', async () => {
    const pending = deferred()
    vi.mocked(locateRelease).mockReturnValueOnce(pending.promise)
    select(1)
    useGruvaxStore.getState().setQuery('record extended')
    pending.resolve(located(1))
    await settle()
    expect(useGruvaxStore.getState().highlight.primaryCube).toEqual(located(1).primary_cube)
    expect(illuminateRecord).toHaveBeenCalledExactlyOnceWith(located(1))
  })

  it.each([false, true])(
    'fully clears locate state after the current selection fails (unavailable=%s)',
    async (unavailable) => {
      const prior: LocateResult = {
        ...located(1),
        primary_cube: unavailable ? null : located(1).primary_cube,
        confidence: unavailable ? 0 : 0.8,
        label_span: [{ unit_id: 1, row: 0, col: 1 }],
        sub_cube_interval: {
          start: 0.8,
          end: 1,
          crosses_boundary: true,
          next_cube: { unit_id: 1, row: 0, col: 2 },
        },
      }
      useGruvaxStore.getState().setLocateResult(prior)
      vi.mocked(locateRelease).mockRejectedValueOnce(new Error('network failure'))
      select(2)
      await settle()
      expect(useGruvaxStore.getState()).toMatchObject({
        selectedReleaseId: 2,
        highlight: { primaryCube: null },
        labelSpan: [],
        subCubeInterval: null,
        confidence: 0,
        shelfLayoutUnavailable: false,
      })
      expect(illuminateRecord).not.toHaveBeenCalled()
    },
  )

  it('lights and illuminates only the latest selection when responses arrive backwards', async () => {
    const first = deferred()
    const second = deferred()
    vi.mocked(locateRelease).mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    select(1)
    select(2)
    second.resolve(located(2))
    await settle()
    first.resolve(located(1))
    await settle()
    expect(useGruvaxStore.getState().highlight.primaryCube).toEqual(located(2).primary_cube)
    expect(illuminateRecord).toHaveBeenCalledExactlyOnceWith(located(2))
  })

  it('does not relight after clear, even when the same record is selected again', async () => {
    const old = deferred()
    const current = deferred()
    vi.mocked(locateRelease).mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise)
    select(1)
    useGruvaxStore.getState().clearSearch()
    select(1)
    old.resolve(located(1))
    await settle()
    expect(useGruvaxStore.getState().highlight.primaryCube).toBeNull()
    expect(illuminateRecord).not.toHaveBeenCalled()
    current.resolve(located(1))
    await settle()
    expect(useGruvaxStore.getState().highlight.primaryCube).toEqual(located(1).primary_cube)
  })

  it('ignores stale rejection rather than clearing a newer successful highlight', async () => {
    const first = deferred()
    vi.mocked(locateRelease).mockReturnValueOnce(first.promise).mockResolvedValueOnce(located(2))
    select(1)
    select(2)
    await settle()
    first.reject(new Error('old network failure'))
    await settle()
    expect(useGruvaxStore.getState().highlight.primaryCube).toEqual(located(2).primary_cube)
    expect(useGruvaxStore.getState().animationToken).toBe(1)
  })

  it.each(['profile', 'clear', 'cancel'] as const)(
    'ignores pending success after %s changes',
    async (change) => {
      const pending = deferred()
      vi.mocked(locateRelease).mockReturnValueOnce(pending.promise)
      select(1)
      if (change === 'profile') useSessionStore.setState({ boundProfileId: 'profile-b' })
      if (change === 'clear') useGruvaxStore.getState().clearSearch()
      if (change === 'cancel') useGruvaxStore.getState().invalidateLocateRequests()
      pending.resolve(located(1))
      await settle()
      expect(useGruvaxStore.getState().highlight.primaryCube).toBeNull()
      expect(illuminateRecord).not.toHaveBeenCalled()
    },
  )
})

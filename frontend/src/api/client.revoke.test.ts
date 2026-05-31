/**
 * client.revoke.test.ts — 403 device_revoked path without mounting KioskView (D-06).
 *
 * RED gate (Task 1 TDD):
 * - Mock fetch to return 403 with body { detail: { type: 'device_revoked' } }.
 * - Call a client.ts wrapper (searchCollection is representative — any caller works).
 * - Assert useSessionStore.getState().revokePending === true after the call.
 * - Assert the call throws Error('device_revoked').
 *
 * KioskView is NOT mounted; no React component is rendered.
 * This proves the revoke signal fires at the fetch layer, independent of component mounting.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useSessionStore } from '../state/sessionStore'

// Import the function under test AFTER mocking is set up
import { searchCollection } from './client'

const REVOKE_403 = {
  status: 403,
  ok: false,
  json: () => Promise.resolve({ detail: { type: 'device_revoked' } }),
  headers: new Headers({ 'Content-Type': 'application/json' }),
} as unknown as Response

const OTHER_403 = {
  status: 403,
  ok: false,
  json: () => Promise.resolve({ detail: { type: 'profile_mismatch' } }),
  headers: new Headers({ 'Content-Type': 'application/json' }),
} as unknown as Response

beforeEach(() => {
  // Reset revokePending to false before each test
  useSessionStore.setState({ revokePending: false })
  vi.restoreAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('client.ts 403 device_revoked intercept', () => {
  it('sets revokePending=true on 403 with detail.type=device_revoked', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(REVOKE_403)

    await expect(searchCollection('blue note')).rejects.toThrow('device_revoked')
    expect(useSessionStore.getState().revokePending).toBe(true)
  })

  it('does NOT set revokePending on a 403 with a different detail.type', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(OTHER_403)

    await expect(searchCollection('blue note')).rejects.toThrow()
    // revokePending must stay false — other 403s are not device_revoked
    expect(useSessionStore.getState().revokePending).toBe(false)
  })

  it('triggerRevoke() is idempotent — second call is a no-op', () => {
    useSessionStore.getState().triggerRevoke()
    useSessionStore.getState().triggerRevoke()
    expect(useSessionStore.getState().revokePending).toBe(true)

    // resetRevoke() sets it back to false
    useSessionStore.getState().resetRevoke()
    expect(useSessionStore.getState().revokePending).toBe(false)

    // Now triggerRevoke() can fire again (idempotent reset-and-retrigger cycle)
    useSessionStore.getState().triggerRevoke()
    expect(useSessionStore.getState().revokePending).toBe(true)
  })
})

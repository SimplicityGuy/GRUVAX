import { act, cleanup, render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminShell } from './AdminShell'
import { adminGetSession } from '../../api/adminClient'
import { useAdminStore } from '../../state/adminStore'

vi.mock('../../api/adminClient', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/adminClient')>()),
  adminGetSession: vi.fn(),
}))

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-01-01T12:00:00Z'))
  useAdminStore.setState({
    isLoggedIn: true,
    csrfToken: 'csrf',
    sessionExpiresAt: Date.now() + 600_000,
    hardCapExpiresAt: Date.now() + 240_000,
    reshuffleDraft: null,
  })
  vi.mocked(adminGetSession).mockReset()
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('authoritative session polls', () => {
  it.each([3600, 240])('a %is server cap controls warning and activity refresh', async (cap) => {
    vi.mocked(adminGetSession).mockResolvedValue({
      expires_at: '2099-01-01T00:00:00Z',
      hard_cap_at: '2099-01-01T01:00:00Z',
      expires_in_seconds: Math.min(600, cap),
      hard_cap_in_seconds: cap,
    })
    const now = Date.now()
    useAdminStore.setState({ hardCapExpiresAt: now + (cap > 300 ? 240 : 1800) * 1000 })
    render(
      <BrowserRouter>
        <AdminShell />
      </BrowserRouter>,
    )
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(useAdminStore.getState().hardCapExpiresAt).toBe(now + cap * 1000)
    expect(useAdminStore.getState().sessionExpiresAt).toBe(now + Math.min(600, cap) * 1000)
    if (cap > 300) {
      expect(screen.queryByText('Session ends soon — activity cannot extend it.')).toBeNull()
    } else {
      expect(screen.getByText('Session ends soon — activity cannot extend it.')).toBeInTheDocument()
    }
    vi.mocked(adminGetSession).mockClear()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_001)
    })
    await act(async () => {
      document.dispatchEvent(new KeyboardEvent('keydown'))
    })
    expect(adminGetSession).toHaveBeenCalledTimes(cap > 300 ? 1 : 0)
  })
})

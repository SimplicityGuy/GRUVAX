import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { getSession } from './api/session'
import { useSessionStore } from './state/sessionStore'

vi.mock('./api/session', () => ({ getSession: vi.fn() }))
vi.mock('./routes/kiosk/KioskView', () => ({ KioskView: () => <div>Kiosk route</div> }))
vi.mock('./routes/kiosk/PairView', () => ({ PairView: () => <div>Pair route</div> }))
vi.mock('./routes/ProfilePicker', () => ({ ProfilePicker: () => <div>Picker route</div> }))
vi.mock('./routes/redeem/RedeemPage', () => ({ RedeemPage: () => <div>Redeem route</div> }))
vi.mock('./routes/admin/AdminShell', () => ({ AdminShell: () => <div>Admin route</div> }))

const boundSession = {
  profile_count: 2,
  bound_profile_id: 'profile-a',
  profiles: [],
  is_device_paired: true,
}

beforeEach(() => {
  window.history.replaceState({}, '', '/')
  useSessionStore.setState({
    boundProfileId: null,
    profileCount: 0,
    profiles: [],
    isDevicePaired: false,
    revokePending: false,
  })
  vi.mocked(getSession).mockResolvedValue(boundSession)
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

async function bootstrap() {
  render(<App />)
  await waitFor(() => expect(useSessionStore.getState().boundProfileId).toBe('profile-a'))
}

function pollUnbound(profileCount: number) {
  act(() => {
    useSessionStore.getState().setSession({
      profile_count: profileCount,
      bound_profile_id: null,
      profiles: [],
      is_device_paired: false,
    })
  })
}

describe('runtime binding recovery', () => {
  it.each([0, 2])(
    'routes a paired kiosk to selection with %i remaining profiles',
    async (count) => {
      await bootstrap()
      expect(screen.getByText('Kiosk route')).toBeInTheDocument()
      pollUnbound(count)
      await waitFor(() => expect(window.location.pathname).toBe('/select'))
      expect(screen.getByText('Picker route')).toBeInTheDocument()
    },
  )

  it.each(['/admin/profiles', '/pair', '/redeem/invite'])(
    'preserves intentional %s route on unbind',
    async (path) => {
      await bootstrap()
      act(() => {
        window.history.pushState({}, '', path)
        window.dispatchEvent(new PopStateEvent('popstate'))
      })
      pollUnbound(2)
      await waitFor(() => expect(useSessionStore.getState().boundProfileId).toBeNull())
      expect(window.location.pathname).toBe(path)
    },
  )

  it('keeps ordinary server failure on the current kiosk route', async () => {
    vi.mocked(getSession).mockRejectedValue(new Error('offline'))
    render(<App />)
    await act(async () => {})
    expect(window.location.pathname).toBe('/')
    expect(screen.getByText('Kiosk route')).toBeInTheDocument()
  })

  it('preserves terminal revoke navigation to pairing', async () => {
    await bootstrap()
    vi.useFakeTimers()
    act(() => useSessionStore.getState().triggerRevoke())
    act(() => vi.advanceTimersByTime(2500))
    expect(window.location.pathname).toBe('/pair')
    expect(screen.getByText('Pair route')).toBeInTheDocument()
    expect(useSessionStore.getState().boundProfileId).toBeNull()
  })
})

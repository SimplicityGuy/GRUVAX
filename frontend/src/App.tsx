import { useEffect } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes, useNavigate } from 'react-router'
import { AdminShell } from './routes/admin/AdminShell'
import { BinWidthEditor } from './routes/admin/BinWidthEditor'
import { ConfirmationRoute } from './routes/admin/ConfirmationScreen'
import { CubesGrid } from './routes/admin/CubesGrid'
import { Diagnostics } from './routes/admin/Diagnostics'
import { HistoryView } from './routes/admin/HistoryView'
import Import from './routes/admin/Import'
import { DevicesManager } from './routes/admin/DevicesManager'
import { ProfilesManager } from './routes/admin/ProfilesManager'
import { Settings } from './routes/admin/Settings'
import { ShelfBinList } from './routes/admin/ShelfBinList'
import { Wizard } from './routes/admin/Wizard'
import { KioskView } from './routes/kiosk/KioskView'
import { PairView } from './routes/kiosk/PairView'
import { ProfilePicker } from './routes/ProfilePicker'
import { getSession } from './api/session'
import { useSessionStore } from './state/sessionStore'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

/**
 * App root — wraps with TanStack Query provider and react-router.
 *
 * Routes:
 *   /                           → KioskView (public, no auth)
 *   /select                     → ProfilePicker (browse-binding — no auth, D2-07)
 *   /admin                      → AdminShell (PIN gate on all /admin/* routes)
 *   /admin/settings             → Settings
 *   /admin/profiles             → ProfilesManager (profile list + status badges + drawer)
 *   /admin/cubes                → CubesGrid (list of shelves — SHELF A, SHELF B, …)
 *   /admin/cubes/:unit          → ShelfBinList (bin-card list for one shelf, sketch 002)
 *   /admin/cubes/:unit/:row/:col → BinWidthEditor (focused single-bin width editor, sketch 001)
 *   /admin/history              → HistoryView
 *   /admin/wizard               → Wizard (setup + reshuffle modes, D-01)
 *   /admin/wizard/done          → ConfirmationRoute (post-commit confirmation, D-15)
 *   /admin/import               → Import (stub — 07-05 replaces with real page)
 *   /admin/diagnostics          → Diagnostics (OBS-05/06/07 — phase 08-04)
 *
 * Design tokens are imported in main.tsx (single entry point).
 */

/**
 * AppInner — rendered inside BrowserRouter so useNavigate is available.
 *
 * Bootstrap (D2-08, Pattern 6): on mount, fetch GET /api/session and update
 * the session store. If the response has no bound_profile_id (unbound), redirect
 * to /select. Single-profile auto-bind is handled server-side — the SPA only
 * redirects when truly unbound after the server has had its chance to auto-bind.
 */
function AppInner() {
  const navigate = useNavigate()
  const setSession = useSessionStore((s) => s.setSession)

  useEffect(() => {
    getSession()
      .then((data) => {
        setSession(data)
        const currentPath = window.location.pathname

        // D3-03: if the device fingerprint is already paired (03-03 session extension),
        // stay on '/' — the paired device should go straight to the bound-profile search UI.
        // Never redirect /pair or /admin to '/' — those are intentional destinations.
        if (data.is_device_paired && data.bound_profile_id) {
          if (currentPath !== '/' && !currentPath.startsWith('/admin')) {
            void navigate('/', { replace: true })
          }
          return
        }

        // D2-08: if no bound_profile_id, the SPA must go to /select.
        // Single-profile auto-bind is server-side — server sets the cookie and
        // returns bound_profile_id in the same response, so we only redirect here
        // when the response genuinely has no binding.
        // Exemption: /pair is always allowed (device pairing flow).
        if (!data.bound_profile_id && currentPath !== '/pair' && !currentPath.startsWith('/admin')) {
          void navigate('/select', { replace: true })
        }
      })
      .catch(() => {
        // Degrade gracefully — stay on current route (offline / server down).
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <Routes>
      <Route path="/" element={<KioskView />} />
      <Route path="/pair" element={<PairView />} />
      <Route path="/select" element={<ProfilePicker />} />
      <Route path="/admin" element={<AdminShell />}>
        <Route index element={<Settings />} />
        <Route path="settings" element={<Settings />} />
        <Route path="profiles" element={<ProfilesManager />} />
        <Route path="devices" element={<DevicesManager />} />
        <Route path="cubes" element={<CubesGrid />} />
        <Route path="cubes/:unit" element={<ShelfBinList />} />
        <Route path="cubes/:unit/:row/:col" element={<BinWidthEditor />} />
        <Route path="history" element={<HistoryView />} />
        <Route path="wizard" element={<Wizard />} />
        <Route path="wizard/done" element={<ConfirmationRoute />} />
        <Route path="import" element={<Import />} />
        <Route path="diagnostics" element={<Diagnostics />} />
      </Route>
    </Routes>
  )
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppInner />
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App

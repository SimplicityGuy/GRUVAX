import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router'
import { AdminShell } from './routes/admin/AdminShell'
import { BinWidthEditor } from './routes/admin/BinWidthEditor'
import { ConfirmationRoute } from './routes/admin/ConfirmationScreen'
import { CubesGrid } from './routes/admin/CubesGrid'
import { Diagnostics } from './routes/admin/Diagnostics'
import { HistoryView } from './routes/admin/HistoryView'
import Import from './routes/admin/Import'
import { Settings } from './routes/admin/Settings'
import { ShelfBinList } from './routes/admin/ShelfBinList'
import { Wizard } from './routes/admin/Wizard'
import { KioskView } from './routes/kiosk/KioskView'

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
 *   /admin                      → AdminShell (PIN gate on all /admin/* routes)
 *   /admin/settings             → Settings
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
function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<KioskView />} />
          <Route path="/admin" element={<AdminShell />}>
            <Route index element={<Settings />} />
            <Route path="settings" element={<Settings />} />
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
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App

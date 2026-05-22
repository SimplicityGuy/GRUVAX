import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router'
import { AdminShell } from './routes/admin/AdminShell'
import { CutPointEditor } from './routes/admin/CutPointEditor'
import { CubesGrid } from './routes/admin/CubesGrid'
import { DiffPreviewSheet } from './routes/admin/DiffPreviewSheet'
import { HistoryView } from './routes/admin/HistoryView'
import { Settings } from './routes/admin/Settings'
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
 *   /           → KioskView (public, no auth)
 *   /admin      → AdminShell (PIN gate on all /admin/* routes)
 *   /admin/settings → Settings
 *   /admin/cubes/:unit/:row/:col → CutPointEditor (Phase 5 — replaces Phase 3 first/last form)
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
            <Route path="cubes/:unit/:row/:col" element={<CutPointEditor />} />
            <Route path="preview" element={<DiffPreviewSheet />} />
            <Route path="history" element={<HistoryView />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App

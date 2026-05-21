import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router'
import { AdminShell } from './routes/admin/AdminShell'
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
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App

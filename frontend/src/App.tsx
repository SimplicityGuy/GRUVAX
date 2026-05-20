import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
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
 * App root — wraps with TanStack Query provider and renders the kiosk view.
 * Design tokens are imported in main.tsx (single entry point).
 */
function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <KioskView />
    </QueryClientProvider>
  )
}

export default App

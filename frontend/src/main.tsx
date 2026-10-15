import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ApiError } from './api/client'
import { InstallPrompt } from './components/InstallPrompt'
import { AuthProvider } from './hooks/useAuth'
import { ToastProvider } from './hooks/useToast'
import { AppRoutes } from './routes'
import './styles/tokens.css'
import './styles/base.css'
import './styles/components.css'
import './styles/layout.css'
import './styles/motion.css'
import './styles/login.css'
import './styles/dark.css'
import './styles/themes.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 20_000,
      refetchOnWindowFocus: true,
      // Retrying "not found" or "not allowed" only delays the message the user needs to see.
      retry: (failures, error) => !(error instanceof ApiError && error.status >= 400 && error.status < 500) && failures < 2,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ToastProvider>
          <AuthProvider>
            <AppRoutes />
            <InstallPrompt />
          </AuthProvider>
        </ToastProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)

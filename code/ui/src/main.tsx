import '@/index.css'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, Link, Navigate } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { AppShell } from '@/components/layout/app-shell'
import { ThemeProvider } from '@/components/theme-provider'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { ConnectionsPage } from '@/pages/connections/connections-page'
import { JobsPage } from '@/pages/jobs/jobs-page'

// Form pages carry the editor and most form widgets; load them on first visit.
const jobWizard = () => import('@/pages/jobs/job-wizard-page').then((m) => ({ Component: m.JobWizardPage }))
const connectionForm = () =>
  import('@/pages/connections/connection-form-page').then((m) => ({ Component: m.ConnectionFormPage }))

const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/jobs" replace /> },
      { path: 'jobs', element: <JobsPage /> },
      { path: 'jobs/new', lazy: jobWizard },
      { path: 'jobs/:name/edit', lazy: jobWizard },
      { path: 'connections', element: <ConnectionsPage /> },
      { path: 'connections/new', lazy: connectionForm },
      { path: 'connections/:name/edit', lazy: connectionForm },
      {
        path: '*',
        element: (
          <p className="text-muted-foreground">
            Page not found. <Link to="/jobs" className="underline">Go to jobs</Link>
          </p>
        ),
      },
    ],
  },
])

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } })

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <RouterProvider router={router} />
          <Toaster richColors />
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)

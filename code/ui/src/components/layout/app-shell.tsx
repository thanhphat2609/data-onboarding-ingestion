import { Fragment } from 'react'
import { Link, Outlet, useLocation } from 'react-router'
import { api } from '@/api/client'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { ThemeToggle } from '@/components/theme-toggle'
import { Badge } from '@/components/ui/badge'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import { Separator } from '@/components/ui/separator'
import { SidebarInset, SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar'

const LABELS: Record<string, string> = { jobs: 'Jobs', connections: 'Connections', new: 'New', edit: 'Edit' }

function Crumbs() {
  const parts = useLocation().pathname.split('/').filter(Boolean)
  return (
    <Breadcrumb>
      <BreadcrumbList>
        {parts.map((part, i) => {
          const to = '/' + parts.slice(0, i + 1).join('/')
          const label = LABELS[part] ?? part
          const last = i === parts.length - 1
          return (
            <Fragment key={to}>
              {i > 0 && <BreadcrumbSeparator />}
              <BreadcrumbItem>
                {last ? <BreadcrumbPage>{label}</BreadcrumbPage> : <BreadcrumbLink render={<Link to={to} />}>{label}</BreadcrumbLink>}
              </BreadcrumbItem>
            </Fragment>
          )
        })}
      </BreadcrumbList>
    </Breadcrumb>
  )
}

export function AppShell() {
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center gap-2 border-b bg-background/80 px-4 backdrop-blur">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="mr-2 data-vertical:h-4 data-vertical:self-center" />
          <Crumbs />
          <div className="ml-auto flex items-center gap-2">
            {api.mode === 'mock' && (
              <Badge variant="outline" title="Data is stored in this browser only; nothing reaches Airflow yet">
                Mock API
              </Badge>
            )}
            <ThemeToggle />
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 p-4 md:p-6">
          <Outlet />
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}

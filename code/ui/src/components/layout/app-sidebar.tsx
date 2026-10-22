import { ActivityIcon, DatabaseIcon, ExternalLinkIcon, WindIcon, WorkflowIcon } from 'lucide-react'
import { NavLink, useLocation } from 'react-router'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from '@/components/ui/sidebar'
import { serviceUrls } from '@/lib/service-urls'

const NAV = [
  { to: '/jobs', label: 'Jobs', icon: WorkflowIcon },
  { to: '/connections', label: 'Connections', icon: DatabaseIcon },
]

const PLATFORM = [
  { href: serviceUrls.airflow, label: 'Airflow', icon: WindIcon },
  { href: serviceUrls.flink, label: 'Flink web UI', icon: ActivityIcon },
]

export function AppSidebar() {
  const { pathname } = useLocation()

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" render={<NavLink to="/jobs" />}>
              <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <WorkflowIcon className="size-4" />
              </div>
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-semibold">Data Onboarding</span>
                <span className="truncate text-xs text-muted-foreground">Ingestion</span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Pipelines</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {NAV.map((item) => (
                <SidebarMenuItem key={item.to}>
                  <SidebarMenuButton
                    tooltip={item.label}
                    isActive={pathname.startsWith(item.to)}
                    render={<NavLink to={item.to} />}
                  >
                    <item.icon />
                    <span>{item.label}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel>Platform</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {PLATFORM.map((item) => (
                <SidebarMenuItem key={item.label}>
                  <SidebarMenuButton
                    tooltip={item.label}
                    render={<a href={item.href} target="_blank" rel="noreferrer" />}
                  >
                    <item.icon />
                    <span>{item.label}</span>
                    <ExternalLinkIcon className="ml-auto size-3 opacity-50" />
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <div className="flex items-center gap-2 rounded-md px-2 py-1.5 text-xs text-muted-foreground group-data-[collapsible=icon]:hidden">
          <span className="size-2 rounded-full bg-amber-500" />
          non-prod
        </div>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}

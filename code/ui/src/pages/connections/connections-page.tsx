import { DatabaseIcon, PlusIcon } from 'lucide-react'
import { Link } from 'react-router'
import { useConnections, useJobs } from '@/api/hooks'
import { PageHeader } from '@/components/page-header'
import { Dimmed, InactiveRow, StatusBadge } from '@/components/inactive-row'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

export function ConnectionsPage() {
  const connections = useConnections()
  const jobs = useJobs()
  const jobCount = (name: string) => jobs.data?.filter((s) => s.job.connection === name).length ?? 0

  return (
    <>
      <PageHeader
        title="Connections"
        description="Sources onboarded by the DE team. Jobs can only read through these connections."
        actions={
          <Button nativeButton={false} render={<Link to="/connections/new" />}>
            <PlusIcon /> New connection
          </Button>
        }
      />
      <Card className="py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-4">Connection</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Server</TableHead>
              <TableHead>Owner</TableHead>
              <TableHead>Max concurrent runs</TableHead>
              <TableHead className="pr-4 text-right">Jobs</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {connections.isPending && (
              <TableRow>
                <TableCell colSpan={6} className="pl-4">
                  <Skeleton className="h-8 w-full" />
                </TableCell>
              </TableRow>
            )}
            {connections.data?.map((c) =>
              c.pending ? (
                <InactiveRow key={c.name} kind="connection" pull={c.pending}>
                  <TableCell className="pl-4">
                    <Dimmed>
                      <span className="font-medium">{c.name}</span>
                      <div>
                        <Badge variant="outline" className="mt-1">
                          {c.template}
                        </Badge>
                      </div>
                    </Dimmed>
                  </TableCell>
                  <TableCell>
                    <StatusBadge active={false} />
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    <Dimmed>
                      {String(c.params.host ?? '')}
                      {c.params.database ? ` / ${String(c.params.database)}` : ''}
                    </Dimmed>
                  </TableCell>
                  <TableCell>
                    <Dimmed>{c.owner}</Dimmed>
                  </TableCell>
                  <TableCell>
                    <Dimmed>{c.limits?.max_concurrent_runs ?? 2}</Dimmed>
                  </TableCell>
                  <TableCell className="pr-4 text-right">
                    <Dimmed>0</Dimmed>
                  </TableCell>
                </InactiveRow>
              ) : (
              <TableRow key={c.name}>
                <TableCell className="pl-4">
                  <Link to={`/connections/${c.name}/edit`} className="font-medium hover:underline">
                    {c.name}
                  </Link>
                  <div>
                    <Badge variant="outline" className="mt-1">
                      {c.template}
                    </Badge>
                  </div>
                </TableCell>
                <TableCell>
                  <StatusBadge active />
                </TableCell>
                <TableCell className="font-mono text-xs">
                  {String(c.params.host ?? '')}
                  {c.params.database ? ` / ${String(c.params.database)}` : ''}
                </TableCell>
                <TableCell>{c.owner}</TableCell>
                <TableCell>{c.limits?.max_concurrent_runs ?? 2}</TableCell>
                <TableCell className="pr-4 text-right">{jobCount(c.name)}</TableCell>
              </TableRow>
              ),
            )}
            {connections.data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="py-12 text-center text-muted-foreground">
                  <DatabaseIcon className="mx-auto mb-2 size-6" />
                  No connections yet.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>
    </>
  )
}

import { ExternalLinkIcon, FileWarningIcon, MoreHorizontalIcon, PlusIcon, WorkflowIcon } from 'lucide-react'
import { Link, useNavigate } from 'react-router'
import { useInvalidFiles, useJobs } from '@/api/hooks'
import type { JobSummary } from '@/api/types'
import { PageHeader } from '@/components/page-header'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { describeSchedule } from '@/lib/schedule'
import { airflowDagUrl } from '@/lib/service-urls'
import { downloadText, jobToYaml } from '@/lib/yaml'

export function JobsPage() {
  const jobs = useJobs()
  const invalid = useInvalidFiles()

  return (
    <>
      <PageHeader
        title="Ingestion jobs"
        description={
          <>
            Saving a job opens a pull request on the orchestration repository; after the merge it becomes the Airflow DAG{' '}
            <code className="font-mono">ingest__&lt;name&gt;</code>, where it is run and monitored.
          </>
        }
        actions={
          <Button nativeButton={false} render={<Link to="/jobs/new" />}>
            <PlusIcon /> New job
          </Button>
        }
      />

      {!!invalid.data?.length && (
        <Alert variant="destructive" className="mb-4">
          <FileWarningIcon />
          <AlertTitle>
            {invalid.data.length} job file{invalid.data.length > 1 ? 's are' : ' is'} invalid and can't be used
          </AlertTitle>
          <AlertDescription>
            <ul className="mt-1 grid gap-0.5">
              {invalid.data.map((f) => (
                <li key={f.path}>
                  <span className="font-mono">{f.path}</span>: {f.error}
                </li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      <Card className="py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-4">Job</TableHead>
              <TableHead>Connection</TableHead>
              <TableHead>Schedule</TableHead>
              <TableHead>Destination</TableHead>
              <TableHead className="w-0" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {jobs.isPending &&
              [0, 1, 2].map((i) => (
                <TableRow key={i}>
                  <TableCell colSpan={5} className="pl-4">
                    <Skeleton className="h-8 w-full" />
                  </TableCell>
                </TableRow>
              ))}
            {jobs.data?.map((summary) => <JobRow key={summary.job.name} summary={summary} />)}
            {jobs.data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="py-12 text-center text-muted-foreground">
                  <WorkflowIcon className="mx-auto mb-2 size-6" />
                  No jobs yet. Create one; its pull request creates the DAG.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>
    </>
  )
}

function JobRow({ summary }: { summary: JobSummary }) {
  const { job, dagId } = summary
  const navigate = useNavigate()
  const editUrl = `/jobs/${job.name}/edit`

  return (
    <TableRow>
      <TableCell className="pl-4">
        <Link to={editUrl} className="font-medium hover:underline">
          {job.name}
        </Link>
        <div className="font-mono text-xs text-muted-foreground">{dagId}</div>
      </TableCell>
      <TableCell>
        <Badge variant="secondary">{job.connection}</Badge>
      </TableCell>
      <TableCell>
        <div>{describeSchedule(job.schedule)}</div>
        {job.schedule && <div className="font-mono text-xs text-muted-foreground">{job.schedule}</div>}
      </TableCell>
      <TableCell>
        <div className="font-mono text-xs">{String(job.sink.params.path ?? '')}</div>
        <div className="text-xs text-muted-foreground">{job.sink.template}</div>
      </TableCell>
      <TableCell className="pr-4">
        <div className="flex items-center justify-end gap-1">
          <Button
            variant="outline"
            size="sm"
            onClick={() => window.open(airflowDagUrl(dagId), '_blank', 'noreferrer')}
          >
            <ExternalLinkIcon /> Airflow
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label="More actions" />}>
              <MoreHorizontalIcon />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => navigate(editUrl)}>Edit</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => downloadText(`${job.name}.yaml`, jobToYaml(job))}>
                Export YAML
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </TableCell>
    </TableRow>
  )
}

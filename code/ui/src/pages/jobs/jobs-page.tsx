import { FileWarningIcon, MoreHorizontalIcon, PlayIcon, PlusIcon, WorkflowIcon } from 'lucide-react'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'
import { useInvalidFiles, useJobs, useTriggerRun } from '@/api/hooks'
import type { JobSummary } from '@/api/types'
import { PageHeader } from '@/components/page-header'
import { RunDots } from '@/components/run-dots'
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
            Each job file becomes its own Airflow DAG named <code className="font-mono">ingest__&lt;name&gt;</code>.
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
            {invalid.data.length} job file{invalid.data.length > 1 ? 's are' : ' is'} invalid and not loaded by Airflow
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
              <TableHead>Recent runs</TableHead>
              <TableHead className="w-0" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {jobs.isPending &&
              [0, 1, 2].map((i) => (
                <TableRow key={i}>
                  <TableCell colSpan={6} className="pl-4">
                    <Skeleton className="h-8 w-full" />
                  </TableCell>
                </TableRow>
              ))}
            {jobs.data?.map((summary) => <JobRow key={summary.job.name} summary={summary} />)}
            {jobs.data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="py-12 text-center text-muted-foreground">
                  <WorkflowIcon className="mx-auto mb-2 size-6" />
                  No jobs yet. Create one to get your first DAG.
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
  const { job, dagId, runs } = summary
  const navigate = useNavigate()
  const trigger = useTriggerRun()
  const editUrl = `/jobs/${job.name}/edit`

  const runNow = () =>
    trigger.mutate(job.name, {
      onSuccess: (run) => toast.success(`Triggered ${dagId}`, { description: `ingest_date ${run.ingestDate}` }),
      onError: (e) => toast.error('Could not trigger the run', { description: e.message }),
    })

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
      <TableCell>
        <RunDots runs={runs} />
      </TableCell>
      <TableCell className="pr-4">
        <div className="flex items-center justify-end gap-1">
          <Button variant="outline" size="sm" onClick={runNow} disabled={trigger.isPending}>
            <PlayIcon /> Run now
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label="More actions" />}>
              <MoreHorizontalIcon />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => navigate(editUrl)}>Edit</DropdownMenuItem>
              <DropdownMenuItem onClick={() => window.open(airflowDagUrl(dagId), '_blank', 'noreferrer')}>
                Open in Airflow
              </DropdownMenuItem>
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

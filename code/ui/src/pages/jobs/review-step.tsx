import { LockIcon, SparklesIcon } from 'lucide-react'
import type { IngestionJob } from '@/api/types'
import { Field } from '@/components/field'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { YamlPanel } from '@/components/yaml-panel'
import { dagId, suggestJobName } from '@/lib/naming'
import { describeSchedule, frequencyOf } from '@/lib/schedule'
import { findSinkTemplate, renderTemplate } from '@/lib/templates'
import { jobToYaml } from '@/lib/yaml'
import type { JobDraft } from '@/pages/jobs/job-draft'

interface ReviewStepProps {
  draft: JobDraft
  job: IngestionJob
  update: (patch: Partial<JobDraft>) => void
  errors: Record<string, string>
  isNew: boolean
}

export function ReviewStep({ draft, job, update, errors, isNew }: ReviewStepProps) {
  const suggestion = suggestJobName(draft.connection, draft.query, frequencyOf(job.schedule))
  const sink = findSinkTemplate(job.sink.template)

  return (
    <div className="grid items-start gap-4 lg:grid-cols-2">
      <div className="grid gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Job</CardTitle>
            <CardDescription>The name is the file name and the DAG id, and cannot change later.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <Field
              label="Name"
              htmlFor="job-name"
              required
              error={errors.name}
              description={
                <>
                  Airflow DAG <code className="font-mono">{dagId(job.name || '<name>')}</code> · pattern{' '}
                  <code className="font-mono">&lt;system&gt;-&lt;dataset&gt;-&lt;frequency&gt;</code>
                </>
              }
            >
              <div className="flex gap-2">
                <div className="relative flex-1">
                  {!isNew && (
                    <LockIcon className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
                  )}
                  <Input
                    id="job-name"
                    className={isNew ? 'font-mono' : 'pl-8 font-mono'}
                    value={job.name}
                    disabled={!isNew}
                    onChange={(e) => update({ name: e.target.value.trim(), nameEdited: true })}
                  />
                </div>
                {isNew && draft.nameEdited && job.name !== suggestion && (
                  <Button variant="outline" onClick={() => update({ nameEdited: false })}>
                    <SparklesIcon /> Suggest
                  </Button>
                )}
              </div>
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Owner" htmlFor="job-owner" required error={errors.owner} description="Team or person accountable">
                <Input id="job-owner" value={draft.owner} placeholder="data-team" onChange={(e) => update({ owner: e.target.value })} />
              </Field>
              <Field label="Tags" htmlFor="job-tags" error={errors.tags} description="Comma separated; added to the DAG">
                <Input id="job-tags" value={draft.tags} placeholder="crm, daily" onChange={(e) => update({ tags: e.target.value })} />
              </Field>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-2 text-sm">
              <dt className="text-muted-foreground">Connection</dt>
              <dd>{job.connection}</dd>
              <dt className="text-muted-foreground">Destination</dt>
              <dd className="font-mono text-xs break-all">{sink ? renderTemplate(sink.uri, draft.sinkParams) : job.sink.template}</dd>
              <dt className="text-muted-foreground">Schedule</dt>
              <dd>{describeSchedule(job.schedule)}</dd>
              <dt className="text-muted-foreground">Row count check</dt>
              <dd>{draft.rowCount}</dd>
              <dt className="text-muted-foreground">Timeout · retries</dt>
              <dd>
                {draft.timeout} · {draft.retries}
              </dd>
            </dl>
          </CardContent>
        </Card>
      </div>

      <YamlPanel path={`pipelines/jobs/${job.name || '<name>'}.yaml`} yaml={jobToYaml(job)} />
    </div>
  )
}

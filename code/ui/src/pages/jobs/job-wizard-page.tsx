import { CheckIcon, ChevronLeftIcon, ChevronRightIcon, SaveIcon } from 'lucide-react'
import { cn } from 'cn'
import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import { toastSaved } from '@/lib/saved-toast'
import { api } from '@/api/client'
import { useConnections, useJob, useJobs, useSaveJob } from '@/api/hooks'
import type { Connection, IngestionJob, QueryPreview, SqlValidation } from '@/api/types'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { dagId } from '@/lib/naming'
import {
  draftErrors,
  draftFromJob,
  draftToJob,
  emptyDraft,
  stepHasErrors,
  STEPS,
  type JobDraft,
} from '@/pages/jobs/job-draft'
import { ReviewStep } from '@/pages/jobs/review-step'
import { ScheduleStep } from '@/pages/jobs/schedule-step'
import { SinkStep } from '@/pages/jobs/sink-step'
import { SourceStep } from '@/pages/jobs/source-step'

export function JobWizardPage() {
  const { name } = useParams()
  const job = useJob(name)
  const connections = useConnections()
  if ((name && job.isPending) || connections.isPending) return <Skeleton className="h-96 w-full" />
  if (job.isError) return <p className="text-destructive">{job.error.message}</p>
  return <JobWizard key={name ?? 'new'} initial={job.data} connections={connections.data ?? []} />
}

function JobWizard({ initial, connections }: { initial?: IngestionJob; connections: Connection[] }) {
  const isNew = !initial
  const navigate = useNavigate()
  const jobs = useJobs()
  const saveMutation = useSaveJob()

  const [draft, setDraft] = useState<JobDraft>(() => {
    if (!initial) return emptyDraft()
    const template = connections.find((c) => c.name === initial.connection)?.template ?? ''
    return draftFromJob(initial, template)
  })
  const [step, setStep] = useState(0)
  const [reached, setReached] = useState(isNew ? 0 : STEPS.length - 1)
  const [showErrors, setShowErrors] = useState(false)

  // Validation and preview belong to the exact query text they were run on.
  const [validation, setValidation] = useState<{ query: string; result: SqlValidation } | null>(null)
  const [validating, setValidating] = useState(false)
  const [preview, setPreview] = useState<QueryPreview | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)

  const job = useMemo(() => draftToJob(draft), [draft])
  const existingNames = jobs.data?.map((s) => s.job.name) ?? []
  const errors = draftErrors(draft, existingNames, isNew)
  const currentValidation = validation?.query === draft.query ? validation.result : null
  const visibleErrors = showErrors ? errors : {}

  const update = (patch: Partial<JobDraft>) => setDraft((d) => ({ ...d, ...patch }))

  const validate = async (): Promise<SqlValidation | null> => {
    setValidating(true)
    try {
      const result = await api.validateSql(draft.connection, draft.query)
      setValidation({ query: draft.query, result })
      return result
    } catch (e) {
      toast.error('Validation failed', { description: (e as Error).message })
      return null
    } finally {
      setValidating(false)
    }
  }

  const runPreview = async () => {
    setPreviewing(true)
    setPreviewError(null)
    try {
      const checked = currentValidation ?? (await validate())
      if (!checked?.ok) return
      setPreview(await api.previewQuery(draft.connection, draft.query))
    } catch (e) {
      setPreviewError((e as Error).message)
    } finally {
      setPreviewing(false)
    }
  }

  const next = async () => {
    setShowErrors(true)
    if (stepHasErrors(errors, step)) return
    if (step === 0) {
      const checked = currentValidation ?? (await validate())
      if (!checked?.ok) return
    }
    setShowErrors(false)
    setStep(step + 1)
    setReached((r) => Math.max(r, step + 1))
  }

  const save = () => {
    setShowErrors(true)
    const firstInvalid = STEPS.findIndex((_, i) => stepHasErrors(errors, i))
    if (firstInvalid >= 0) {
      setStep(firstInvalid)
      return
    }
    saveMutation.mutate(
      { job, isNew },
      {
        onSuccess: (saved) => {
          toastSaved(`job ${job.name}`, saved.pullRequest, `Airflow DAG ${dagId(job.name)} appears after the merge`)
          navigate('/jobs')
        },
        onError: (e) => toast.error('Could not save', { description: e.message }),
      },
    )
  }

  const last = step === STEPS.length - 1

  return (
    <>
      <PageHeader
        title={isNew ? 'New ingestion job' : initial.name}
        description={isNew ? 'Four steps; the result is one YAML file in a pull request, and after the merge one Airflow DAG.' : `Airflow DAG ${dagId(initial.name)}`}
      />

      <ol className="mb-6 grid gap-2 sm:grid-cols-4">
        {STEPS.map((s, i) => {
          const done = i < step || (i <= reached && i !== step && !stepHasErrors(errors, i))
          return (
            <li key={s.id}>
              <button
                type="button"
                disabled={i > reached}
                onClick={() => setStep(i)}
                className={cn(
                  'flex w-full items-center gap-3 rounded-lg border p-3 text-left transition-colors enabled:hover:bg-muted/50 disabled:opacity-60',
                  i === step && 'border-primary ring-1 ring-primary',
                )}
              >
                <span
                  className={cn(
                    'flex size-7 shrink-0 items-center justify-center rounded-full border text-xs font-medium',
                    i === step && 'border-primary bg-primary text-primary-foreground',
                    done && i !== step && 'border-emerald-600 bg-emerald-600 text-white',
                  )}
                >
                  {done && i !== step ? <CheckIcon className="size-3.5" /> : i + 1}
                </span>
                <span className="grid leading-tight">
                  <span className="text-sm font-medium">{s.title}</span>
                  <span className="text-xs text-muted-foreground">{s.description}</span>
                </span>
              </button>
            </li>
          )
        })}
      </ol>

      {step === 0 && (
        <SourceStep
          draft={draft}
          update={update}
          errors={visibleErrors}
          connections={connections}
          validation={currentValidation}
          validating={validating}
          onValidate={validate}
          preview={preview}
          previewing={previewing}
          previewError={previewError}
          onPreview={runPreview}
        />
      )}
      {step === 1 && <SinkStep draft={draft} update={update} errors={visibleErrors} />}
      {step === 2 && <ScheduleStep draft={draft} update={update} errors={visibleErrors} />}
      {step === 3 && <ReviewStep draft={draft} job={job} update={update} errors={visibleErrors} isNew={isNew} />}

      <div className="mt-6 flex items-center justify-between border-t pt-4">
        <Button variant="ghost" onClick={() => (step === 0 ? navigate('/jobs') : setStep(step - 1))}>
          <ChevronLeftIcon /> {step === 0 ? 'Cancel' : 'Back'}
        </Button>
        {last ? (
          <Button onClick={save} disabled={saveMutation.isPending}>
            <SaveIcon /> Save job
          </Button>
        ) : (
          <Button onClick={next} disabled={validating}>
            Next <ChevronRightIcon />
          </Button>
        )}
      </div>
    </>
  )
}

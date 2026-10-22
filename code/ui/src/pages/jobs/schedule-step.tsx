import { cn } from 'cn'
import type { RowCountPolicy } from '@/api/types'
import { Field } from '@/components/field'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { SCHEDULE_PRESETS, SCHEDULE_TIMEZONE } from '@/lib/schedule'
import type { JobDraft } from '@/pages/jobs/job-draft'

interface ScheduleStepProps {
  draft: JobDraft
  update: (patch: Partial<JobDraft>) => void
  errors: Record<string, string>
}

const ROW_COUNT_ITEMS: { label: string; value: RowCountPolicy }[] = [
  { label: 'Exact match', value: 'exact' },
  { label: 'Within a tolerance', value: 'tolerance' },
  { label: 'Skip (no COUNT on the source)', value: 'skip' },
]

export function ScheduleStep({ draft, update, errors }: ScheduleStepProps) {
  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Schedule</CardTitle>
          <CardDescription>
            Becomes the schedule of the Airflow DAG, in {SCHEDULE_TIMEZONE}. Every job can also be run on demand.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div role="radiogroup" className="grid gap-2 sm:grid-cols-3 lg:grid-cols-5">
            {SCHEDULE_PRESETS.map((preset) => {
              const selected = draft.scheduleId === preset.id
              return (
                <button
                  key={preset.id}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => update({ scheduleId: preset.id })}
                  className={cn(
                    'grid gap-1 rounded-lg border p-3 text-left transition-colors hover:bg-muted/50',
                    selected && 'border-primary ring-1 ring-primary',
                  )}
                >
                  <span className="text-sm font-medium">{preset.label}</span>
                  <span className="text-xs text-muted-foreground">{preset.description}</span>
                  {preset.cron && <span className="font-mono text-xs text-muted-foreground">{preset.cron}</span>}
                </button>
              )
            })}
          </div>
          {draft.scheduleId === 'custom' && (
            <Field label="Cron expression" htmlFor="schedule-cron" required error={errors.customSchedule}>
              <Input
                id="schedule-cron"
                className="font-mono sm:w-80"
                placeholder="30 1 * * *"
                value={draft.customSchedule}
                onChange={(e) => update({ customSchedule: e.target.value })}
              />
            </Field>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Verification and runtime</CardTitle>
          <CardDescription>A run is published only after the written rows match the source count.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Row count check" htmlFor="verify-policy">
            <Select
              items={ROW_COUNT_ITEMS}
              value={draft.rowCount}
              onValueChange={(v) => v && update({ rowCount: v })}
            >
              <SelectTrigger id="verify-policy" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROW_COUNT_ITEMS.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          {draft.rowCount === 'tolerance' && (
            <Field label="Tolerance (%)" htmlFor="verify-tolerance" required error={errors.tolerancePct}>
              <Input
                id="verify-tolerance"
                type="number"
                step="0.1"
                value={draft.tolerancePct}
                onChange={(e) => update({ tolerancePct: e.target.value })}
              />
            </Field>
          )}
          <Field label="Timeout" htmlFor="runtime-timeout" error={errors.timeout} description="The Flink job is cancelled after it">
            <Input id="runtime-timeout" value={draft.timeout} onChange={(e) => update({ timeout: e.target.value })} />
          </Field>
          <Field label="Retries" htmlFor="runtime-retries" error={errors.retries} description="Each retry restarts the whole run">
            <Input id="runtime-retries" type="number" min={0} max={5} value={draft.retries} onChange={(e) => update({ retries: e.target.value })} />
          </Field>
          <Field
            label="Parallelism"
            htmlFor="runtime-parallelism"
            error={errors.parallelism}
            description="Empty: derived from partition_num"
          >
            <Input
              id="runtime-parallelism"
              type="number"
              min={1}
              max={64}
              placeholder="Auto"
              value={draft.parallelism}
              onChange={(e) => update({ parallelism: e.target.value })}
            />
          </Field>
        </CardContent>
      </Card>
    </div>
  )
}

import type { IngestionJob, RowCountPolicy } from '@/api/types'
import { nameError, suggestJobName } from '@/lib/naming'
import { frequencyOf, isValidSchedule, presetFor, SCHEDULE_PRESETS, type SchedulePreset } from '@/lib/schedule'
import {
  findSinkTemplate,
  findSourceTemplate,
  sinkTemplates,
  templateRef,
  validateParams,
  withDefaults,
  withoutDefaults,
} from '@/lib/templates'

/** Flat, form-friendly state of the wizard; converted to an IngestionJob for YAML and saving. */
export interface JobDraft {
  connection: string
  connectionTemplate: string
  query: string
  read: Record<string, unknown>
  sinkTemplate: string
  sinkParams: Record<string, unknown>
  scheduleId: SchedulePreset['id']
  customSchedule: string
  rowCount: RowCountPolicy
  tolerancePct: string
  timeout: string
  retries: string
  parallelism: string
  name: string
  nameEdited: boolean
  owner: string
  tags: string
}

export const STEPS = [
  { id: 'source', title: 'Source', description: 'Connection and query' },
  { id: 'sink', title: 'Destination', description: 'Where the data lands' },
  { id: 'schedule', title: 'Schedule', description: 'When and how it runs' },
  { id: 'review', title: 'Review', description: 'Name, YAML and save' },
] as const

// Which error keys block which step; keys ending in "." are prefixes.
const STEP_FIELDS: string[][] = [
  ['connection', 'query', 'read.'],
  ['sink.'],
  ['customSchedule', 'tolerancePct', 'timeout', 'retries', 'parallelism'],
  ['name', 'owner', 'tags'],
]

export function emptyDraft(): JobDraft {
  const sink = sinkTemplates[0]
  return {
    connection: '',
    connectionTemplate: '',
    query: '',
    read: {},
    sinkTemplate: templateRef(sink),
    sinkParams: withDefaults(sink.params),
    scheduleId: 'daily',
    customSchedule: '',
    rowCount: 'exact',
    tolerancePct: '',
    timeout: '2h',
    retries: '1',
    parallelism: '',
    name: '',
    nameEdited: false,
    owner: '',
    tags: '',
  }
}

export function draftFromJob(job: IngestionJob, connectionTemplate: string): JobDraft {
  const preset = presetFor(job.schedule)
  const source = findSourceTemplate(connectionTemplate)
  const sink = findSinkTemplate(job.sink.template)
  return {
    connection: job.connection,
    connectionTemplate,
    query: job.source.query,
    read: withDefaults(source?.read_params ?? {}, job.source.read),
    sinkTemplate: job.sink.template,
    sinkParams: withDefaults(sink?.params ?? {}, job.sink.params),
    scheduleId: preset.id,
    customSchedule: preset.id === 'custom' ? (job.schedule ?? '') : '',
    rowCount: job.verify?.row_count ?? 'exact',
    tolerancePct: job.verify?.tolerance_pct?.toString() ?? '',
    timeout: job.runtime?.timeout ?? '2h',
    retries: job.runtime?.retries?.toString() ?? '1',
    parallelism: job.runtime?.parallelism?.toString() ?? '',
    name: job.name,
    nameEdited: true,
    owner: job.owner,
    tags: job.tags?.join(', ') ?? '',
  }
}

export function scheduleOf(d: JobDraft): string | undefined {
  if (d.scheduleId === 'custom') return d.customSchedule.trim() || undefined
  return SCHEDULE_PRESETS.find((p) => p.id === d.scheduleId)?.cron
}

export function effectiveName(d: JobDraft): string {
  if (d.nameEdited || !d.connection) return d.name
  return suggestJobName(d.connection, d.query, frequencyOf(scheduleOf(d)))
}

export const parseTags = (tags: string) =>
  tags
    .split(',')
    .map((t) => t.trim().toLowerCase())
    .filter(Boolean)

export function draftToJob(d: JobDraft): IngestionJob {
  const source = findSourceTemplate(d.connectionTemplate)
  const sink = findSinkTemplate(d.sinkTemplate)
  return {
    kind: 'IngestionJob',
    name: effectiveName(d),
    owner: d.owner,
    connection: d.connection,
    source: { query: d.query, read: withoutDefaults(source?.read_params ?? {}, d.read) },
    sink: { template: d.sinkTemplate, params: withoutDefaults(sink?.params ?? {}, d.sinkParams) },
    verify: {
      row_count: d.rowCount === 'exact' ? undefined : d.rowCount,
      tolerance_pct: d.rowCount === 'tolerance' && d.tolerancePct ? Number(d.tolerancePct) : undefined,
    },
    runtime: {
      parallelism: d.parallelism ? Number(d.parallelism) : undefined,
      timeout: d.timeout === '2h' ? undefined : d.timeout,
      retries: d.retries === '1' ? undefined : Number(d.retries),
    },
    schedule: scheduleOf(d),
    tags: parseTags(d.tags),
  }
}

export function draftErrors(d: JobDraft, existingNames: string[], isNew: boolean): Record<string, string> {
  const errors: Record<string, string> = {}
  if (!d.connection) errors.connection = 'Pick a connection'
  if (!d.query.trim()) errors.query = 'Write a query'

  const source = findSourceTemplate(d.connectionTemplate)
  for (const [k, v] of Object.entries(validateParams(source?.read_params ?? {}, d.read))) errors[`read.${k}`] = v
  const sink = findSinkTemplate(d.sinkTemplate)
  for (const [k, v] of Object.entries(validateParams(sink?.params ?? {}, d.sinkParams))) errors[`sink.${k}`] = v

  if (d.scheduleId === 'custom' && !isValidSchedule(d.customSchedule)) {
    errors.customSchedule = 'Five cron fields, for example "30 1 * * *", or a preset like @daily'
  }
  if (d.rowCount === 'tolerance' && !(Number(d.tolerancePct) > 0 && Number(d.tolerancePct) <= 100)) {
    errors.tolerancePct = 'Between 0 and 100'
  }
  if (!/^[1-9][0-9]*(s|m|h)$/.test(d.timeout)) errors.timeout = 'For example 30m or 2h'
  if (!/^[0-5]$/.test(d.retries)) errors.retries = 'Between 0 and 5'
  if (d.parallelism && !/^([1-9]|[1-5][0-9]|6[0-4])$/.test(d.parallelism)) errors.parallelism = 'Between 1 and 64'

  const name = nameError(effectiveName(d), existingNames, isNew)
  if (name) errors.name = name
  if (!d.owner.trim()) errors.owner = 'Required'
  if (parseTags(d.tags).some((t) => !/^[a-z0-9][a-z0-9_-]*$/.test(t))) {
    errors.tags = 'Lowercase letters, digits, "-" and "_"'
  }
  return errors
}

export function stepHasErrors(errors: Record<string, string>, step: number) {
  return Object.keys(errors).some((key) =>
    STEP_FIELDS[step].some((f) => (f.endsWith('.') ? key.startsWith(f) : key === f)),
  )
}

/** Errors under a prefix with the prefix removed, for ParamFields. */
export function prefixed(errors: Record<string, string>, prefix: string) {
  return Object.fromEntries(
    Object.entries(errors)
      .filter(([k]) => k.startsWith(prefix))
      .map(([k, v]) => [k.slice(prefix.length), v]),
  )
}

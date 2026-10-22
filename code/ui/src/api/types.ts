// Mirrors docs/configuration-spec.md and code/templates/schemas/*.json.

export interface Connection {
  kind: 'Connection'
  name: string
  template: string
  owner: string
  params: Record<string, unknown>
  limits?: {
    max_concurrent_runs?: number
    max_partition_num?: number
    run_window?: string
  }
  access?: { groups?: string[] }
}

export type RowCountPolicy = 'exact' | 'tolerance' | 'skip'

export interface IngestionJob {
  kind: 'IngestionJob'
  name: string
  owner: string
  connection: string
  source: { query: string; read?: Record<string, unknown> }
  sink: { template: string; params: Record<string, unknown> }
  verify?: { row_count?: RowCountPolicy; tolerance_pct?: number }
  runtime?: { parallelism?: number; timeout?: string; retries?: number }
  schedule?: string
  tags?: string[]
}

export type RunState = 'queued' | 'running' | 'success' | 'failed'

export interface RunSummary {
  runId: string
  dagId: string
  ingestDate: string
  state: RunState
  startedAt: string
  trigger: 'manual' | 'schedule'
}

export interface JobSummary {
  job: IngestionJob
  dagId: string
  runs: RunSummary[]
}

export interface InvalidFile {
  path: string
  error: string
}

export interface ConnectionTestResult {
  ok: boolean
  message: string
  latencyMs?: number
}

export interface SqlValidation {
  ok: boolean
  mode: 'table' | 'query'
  issues: { severity: 'error' | 'warning'; message: string }[]
}

export interface QueryPreview {
  columns: { name: string; type: string }[]
  rows: unknown[][]
}

export interface IngestionApi {
  readonly mode: 'mock' | 'http'
  listConnections(): Promise<Connection[]>
  getConnection(name: string): Promise<Connection>
  saveConnection(connection: Connection, isNew: boolean): Promise<Connection>
  testConnection(connection: Connection): Promise<ConnectionTestResult>
  listJobs(): Promise<JobSummary[]>
  getJob(name: string): Promise<IngestionJob>
  saveJob(job: IngestionJob, isNew: boolean): Promise<IngestionJob>
  listInvalidFiles(): Promise<InvalidFile[]>
  validateSql(connection: string, query: string): Promise<SqlValidation>
  previewQuery(connection: string, query: string): Promise<QueryPreview>
  triggerRun(jobName: string, ingestDate?: string): Promise<RunSummary>
}

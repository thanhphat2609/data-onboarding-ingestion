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

/** The pull request a save opened on the orchestration repository (ADR-0017); absent when saved to disk only. */
export interface PullRequestRef {
  number: number
  url: string
  branch: string
}

export type Saved<T> = T & { pullRequest?: PullRequestRef }

/** In a list: `pending` is set while the pull request of the save is open (nothing can use the item yet). */
export type Listed<T> = T & { pending?: PullRequestRef }

export interface JobSummary {
  job: IngestionJob
  dagId: string
  pending?: PullRequestRef
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
  listConnections(): Promise<Listed<Connection>[]>
  getConnection(name: string): Promise<Connection>
  saveConnection(connection: Connection, isNew: boolean): Promise<Saved<Connection>>
  testConnection(connection: Connection): Promise<ConnectionTestResult>
  listJobs(): Promise<JobSummary[]>
  getJob(name: string): Promise<IngestionJob>
  saveJob(job: IngestionJob, isNew: boolean): Promise<Saved<IngestionJob>>
  listInvalidFiles(): Promise<InvalidFile[]>
  validateSql(connection: string, query: string): Promise<SqlValidation>
  previewQuery(connection: string, query: string): Promise<QueryPreview>
}

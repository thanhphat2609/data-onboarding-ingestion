// Ingestion API over HTTP (code/control-plane). Same origin: nginx (container) or Vite (dev) proxies /api.

import type {
  Connection,
  ConnectionTestResult,
  IngestionApi,
  IngestionJob,
  InvalidFile,
  JobSummary,
  QueryPreview,
  Saved,
  SqlValidation,
} from '@/api/types'

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`
    try {
      const error = (await response.json()) as { detail?: unknown }
      if (typeof error.detail === 'string') message = error.detail
      // FastAPI request validation: a list of { loc, msg }.
      else if (Array.isArray(error.detail)) message = error.detail.map((d: { msg?: string }) => d.msg).join('; ')
    } catch {
      // Not JSON (for example a proxy error page): keep the status line.
    }
    throw new Error(message)
  }
  return (await response.json()) as T
}

const segment = encodeURIComponent

export const httpApi: IngestionApi = {
  mode: 'http',

  listConnections: () => request<Connection[]>('GET', '/connections'),

  getConnection: (name) => request<Connection>('GET', `/connections/${segment(name)}`),

  saveConnection: (connection, isNew) =>
    isNew
      ? request<Saved<Connection>>('POST', '/connections', connection)
      : request<Saved<Connection>>('PUT', `/connections/${segment(connection.name)}`, connection),

  testConnection: (connection) =>
    request<ConnectionTestResult>('POST', `/connections/${segment(connection.name)}/test`, connection),

  listJobs: () => request<JobSummary[]>('GET', '/jobs'),

  getJob: (name) => request<IngestionJob>('GET', `/jobs/${segment(name)}`),

  saveJob: (job, isNew) =>
    isNew
      ? request<Saved<IngestionJob>>('POST', '/jobs', job)
      : request<Saved<IngestionJob>>('PUT', `/jobs/${segment(job.name)}`, job),

  listInvalidFiles: () => request<InvalidFile[]>('GET', '/invalid-files'),

  validateSql: (connection, query) => request<SqlValidation>('POST', '/sql/validate', { connection, query }),

  previewQuery: (connection, query) => request<QueryPreview>('POST', '/sql/preview', { connection, query }),
}

// In-browser implementation of the Ingestion API, used until the FastAPI service exists.
// State lives in localStorage, so it survives reloads but is private to each browser.

import { checkSql, stripComments } from '@/lib/sql'
import { dagId } from '@/lib/naming'
import type {
  Connection,
  IngestionApi,
  IngestionJob,
  InvalidFile,
  JobSummary,
  QueryPreview,
} from '@/api/types'

const STORAGE_KEY = 'ingestion-ui.mock.v2'

interface MockState {
  connections: Connection[]
  jobs: IngestionJob[]
}

function daysAgo(n: number) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  d.setHours(2, 0, 0, 0)
  return d
}

function seed(): MockState {
  // Like a new prod: nothing exists until it is created in the UI.
  return { connections: [], jobs: [] }
}

function load(): MockState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw) as MockState
  } catch {
    // Storage unavailable or corrupt: start from the seed.
  }
  return seed()
}

let state = load()

function save() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    // Keep working in memory.
  }
}

const delay = <T>(value: T, ms = 300) => new Promise<T>((resolve) => setTimeout(() => resolve(value), ms))

function notFound(kind: string, name: string): never {
  throw new Error(`${kind} "${name}" not found`)
}

// Column types of the seeded SQL Server sample tables (infrastructure/non-prod/sqlserver/seed.sql).
const SAMPLE_COLUMNS: Record<string, string> = {
  customer_id: 'int',
  full_name: 'nvarchar(200)',
  email: 'nvarchar(320)',
  segment_id: 'int',
  segment_name: 'nvarchar(100)',
  is_deleted: 'bit',
  created_at: 'datetime2(3)',
  updated_at: 'datetime2(3)',
}

function previewColumns(query: string): string[] {
  const select = stripComments(query).match(/select\s+(?:top\s+\S+\s+)?([\s\S]*?)\s+from\s/i)?.[1] ?? '*'
  if (select.trim() === '*') return Object.keys(SAMPLE_COLUMNS).filter((c) => c !== 'segment_name')
  return select.split(',').map((part) => {
    const alias = part.trim().match(/(?:\bas\s+)?\[?(\w+)\]?\s*$/i)
    return alias?.[1] ?? part.trim()
  })
}

function sampleValue(column: string, row: number): unknown {
  const type = SAMPLE_COLUMNS[column] ?? 'nvarchar'
  if (type === 'int') return row + 1000
  if (type === 'bit') return false
  if (type.startsWith('datetime')) return daysAgo(row).toISOString().replace('T', ' ').slice(0, 19)
  if (column === 'email') return `customer${row + 1000}@example.com`
  if (column === 'segment_name') return ['Retail', 'SME', 'Enterprise'][row % 3]
  return `Customer ${row + 1000}`
}

export const mockApi: IngestionApi = {
  mode: 'mock',

  listConnections: () => delay([...state.connections]),

  getConnection: async (name) => delay(state.connections.find((c) => c.name === name) ?? notFound('Connection', name)),

  async saveConnection(connection, isNew) {
    const exists = state.connections.some((c) => c.name === connection.name)
    if (isNew && exists) throw new Error(`pipelines/connections/${connection.name}.yaml already exists`)
    if (!isNew && !exists) notFound('Connection', connection.name)
    state = {
      ...state,
      connections: isNew
        ? [...state.connections, connection]
        : state.connections.map((c) => (c.name === connection.name ? connection : c)),
    }
    save()
    return delay(connection)
  },

  async testConnection(connection) {
    const host = String(connection.params.host ?? '')
    if (!host) return delay({ ok: false, message: 'Host is empty' }, 400)
    if (host.includes('invalid')) {
      return delay({ ok: false, message: `Cannot resolve host "${host}" (mock)` }, 900)
    }
    return delay({ ok: true, message: 'Connected to Microsoft SQL Server 2022 (mock)', latencyMs: 42 }, 700)
  },

  listJobs: () =>
    delay(
      state.jobs.map<JobSummary>((job) => ({
        job,
        dagId: dagId(job.name),
      })),
    ),

  getJob: async (name) => delay(state.jobs.find((j) => j.name === name) ?? notFound('Job', name)),

  async saveJob(job, isNew) {
    const exists = state.jobs.some((j) => j.name === job.name)
    if (isNew && exists) throw new Error(`pipelines/jobs/${job.name}.yaml already exists`)
    if (!isNew && !exists) notFound('Job', job.name)
    state = {
      ...state,
      jobs: isNew ? [...state.jobs, job] : state.jobs.map((j) => (j.name === job.name ? job : j)),
    }
    save()
    return delay(job)
  },

  listInvalidFiles: () =>
    delay<InvalidFile[]>([
      {
        path: 'pipelines/jobs/erp-orders.yaml',
        error: 'File name does not match name "erp-orders-hourly"; the DAG was not created (sample)',
      },
    ]),

  async validateSql(connection, query) {
    if (!state.connections.some((c) => c.name === connection)) notFound('Connection', connection)
    const result = checkSql(query)
    return delay({ ok: !result.issues.some((i) => i.severity === 'error'), mode: result.mode, issues: result.issues }, 250)
  },

  async previewQuery(_connection, query) {
    const columns = previewColumns(query)
    const preview: QueryPreview = {
      columns: columns.map((name) => ({ name, type: SAMPLE_COLUMNS[name] ?? 'nvarchar' })),
      rows: Array.from({ length: 10 }, (_, row) => columns.map((c) => sampleValue(c, row))),
    }
    return delay(preview, 600)
  },
}

export function resetMockState() {
  state = seed()
  save()
}

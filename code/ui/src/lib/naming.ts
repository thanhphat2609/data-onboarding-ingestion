import { firstTable } from '@/lib/sql'

export const NAME_PATTERN = /^[a-z][a-z0-9-]{2,62}$/

export const DAG_PREFIX = 'ingest__'

export const dagId = (jobName: string) => `${DAG_PREFIX}${jobName}`

export function slug(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

/** Suggests `<system>-<dataset>-<frequency>` from the connection, the query and the schedule. */
export function suggestJobName(connection: string, query: string, frequency: string): string {
  const system = connection.split('-')[0] || 'source'
  const dataset = slug(firstTable(query) ?? '') || 'dataset'
  return [system, dataset, frequency].filter(Boolean).join('-').slice(0, 63)
}

export function nameError(name: string, existing: string[], isNew: boolean): string | null {
  if (!name) return 'Name is required'
  if (!NAME_PATTERN.test(name)) {
    return 'Use 3-63 lowercase letters, digits or "-", starting with a letter'
  }
  if (isNew && existing.includes(name)) return 'A file with this name already exists'
  return null
}

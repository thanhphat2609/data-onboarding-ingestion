import { stringify } from 'yaml'
import type { Connection, IngestionJob } from '@/api/types'

/** Drops undefined values, empty strings, empty arrays and empty objects. */
export function prune<T>(value: T): T | undefined {
  if (Array.isArray(value)) {
    return value.length ? value : undefined
  }
  if (value && typeof value === 'object') {
    const entries = Object.entries(value)
      .map(([k, v]) => [k, prune(v)] as const)
      .filter(([, v]) => v !== undefined)
    return entries.length ? (Object.fromEntries(entries) as T) : undefined
  }
  return value === '' || value === null ? undefined : value
}

function toYaml(doc: object) {
  return stringify(prune(doc), { lineWidth: 0, blockQuote: 'literal' })
}

export function connectionToYaml(c: Connection) {
  // Key order follows docs/configuration-spec.md.
  return toYaml({
    kind: c.kind,
    name: c.name,
    template: c.template,
    owner: c.owner,
    params: c.params,
    limits: c.limits,
    access: c.access,
  })
}

export function jobToYaml(j: IngestionJob) {
  return toYaml({
    kind: j.kind,
    name: j.name,
    owner: j.owner,
    connection: j.connection,
    source: { query: j.source.query.trim() + '\n', read: j.source.read },
    sink: j.sink,
    verify: j.verify,
    runtime: j.runtime,
    schedule: j.schedule,
    tags: j.tags,
  })
}

export function downloadText(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'application/yaml' }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

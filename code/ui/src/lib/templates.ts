import { parse } from 'yaml'

export type ParamType = 'string' | 'int' | 'bool' | 'enum' | 'secret_ref' | 'duration' | 'list'

export interface ParamDef {
  type: ParamType
  required?: boolean
  default?: unknown
  min?: number
  max?: number
  values?: string[]
  description?: string
}

export type ParamDefs = Record<string, ParamDef>

export interface SourceTemplate {
  kind: 'SourceTemplate'
  name: string
  version: number
  connector: string
  dialect: string
  connection_params: ParamDefs
  read_params: ParamDefs
}

export interface SinkTemplate {
  kind: 'SinkTemplate'
  name: string
  version: number
  format: string
  uri: string
  params: ParamDefs
  partition_by: string[]
  publish: string
}

// Templates are read from the repository at build time; the API will serve them later.
const sourceFiles = import.meta.glob<string>('@templates/sources/*.yaml', {
  query: '?raw',
  import: 'default',
  eager: true,
})
const sinkFiles = import.meta.glob<string>('@templates/sinks/*.yaml', {
  query: '?raw',
  import: 'default',
  eager: true,
})

export const sourceTemplates: SourceTemplate[] = Object.values(sourceFiles).map(
  (text) => parse(text) as SourceTemplate,
)
export const sinkTemplates: SinkTemplate[] = Object.values(sinkFiles).map(
  (text) => parse(text) as SinkTemplate,
)

export const templateRef = (t: { name: string; version: number }) => `${t.name}@${t.version}`

export const findSourceTemplate = (ref: string) => sourceTemplates.find((t) => templateRef(t) === ref)
export const findSinkTemplate = (ref: string) => sinkTemplates.find((t) => templateRef(t) === ref)

export function humanize(key: string): string {
  const text = key.replace(/_/g, ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export const SECRET_REF_PATTERN = /^(env|kv):\/\/\S+$/
const DURATION_PATTERN = /^[1-9][0-9]*(s|m|h)$/

export type ParamErrors = Record<string, string>

/** Validates values against template parameter declarations; returns one message per invalid field. */
export function validateParams(defs: ParamDefs, values: Record<string, unknown>): ParamErrors {
  const errors: ParamErrors = {}
  for (const [key, def] of Object.entries(defs)) {
    const value = values[key]
    const empty = value === undefined || value === null || value === ''
    if (empty) {
      if (def.required) errors[key] = 'Required'
      continue
    }
    switch (def.type) {
      case 'int': {
        const n = Number(value)
        if (!Number.isInteger(n)) errors[key] = 'Must be a whole number'
        else if (def.min !== undefined && n < def.min) errors[key] = `Must be at least ${def.min}`
        else if (def.max !== undefined && n > def.max) errors[key] = `Must be at most ${def.max}`
        break
      }
      case 'enum':
        if (!def.values?.includes(String(value))) errors[key] = `One of: ${def.values?.join(', ')}`
        break
      case 'secret_ref':
        if (!SECRET_REF_PATTERN.test(String(value))) {
          errors[key] = 'Use a reference: env://VAR or kv://vault/secret'
        }
        break
      case 'duration':
        if (!DURATION_PATTERN.test(String(value))) errors[key] = 'For example 30s, 15m or 2h'
        break
    }
  }
  return errors
}

/** Returns the template defaults merged with the given values. */
export function withDefaults(defs: ParamDefs, values: Record<string, unknown> = {}) {
  const result: Record<string, unknown> = {}
  for (const [key, def] of Object.entries(defs)) {
    if (def.default !== undefined) result[key] = def.default
  }
  return { ...result, ...values }
}

/** Keeps only values that differ from the template defaults, so YAML stays short. */
export function withoutDefaults(defs: ParamDefs, values: Record<string, unknown> = {}) {
  const result: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(values)) {
    if (value === undefined || value === '' || value === null) continue
    if (defs[key]?.default === value) continue
    result[key] = value
  }
  return result
}

/** Renders a `{{ param }}` template string, for example a sink URI. */
export function renderTemplate(text: string, values: Record<string, unknown>) {
  return text.replace(/\{\{\s*(\w+)\s*\}\}/g, (_, key: string) => String(values[key] ?? `<${key}>`))
}

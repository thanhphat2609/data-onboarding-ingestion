// Lightweight checks for the mock API and instant feedback in the editor.
// The real validation is AST-based (sqlglot) in the Ingestion API, see ADR-0005.

export interface SqlIssue {
  severity: 'error' | 'warning'
  message: string
}

export interface SqlCheck {
  issues: SqlIssue[]
  mode: 'table' | 'query'
  tables: string[]
}

const FORBIDDEN = [
  'insert', 'update', 'delete', 'merge', 'drop', 'alter', 'create', 'truncate',
  'exec', 'execute', 'grant', 'revoke', 'deny', 'backup', 'restore', 'dbcc',
  'openrowset', 'openquery', 'opendatasource', 'waitfor', 'shutdown',
]

export function stripComments(query: string) {
  return query.replace(/--[^\n]*/g, ' ').replace(/\/\*[\s\S]*?\*\//g, ' ')
}

/** Removes string literals so that keywords inside them are ignored. */
function stripLiterals(query: string) {
  return query.replace(/N?'(?:[^']|'')*'/g, "''")
}

export function referencedTables(query: string): string[] {
  const clean = stripLiterals(stripComments(query))
  const tables: string[] = []
  for (const match of clean.matchAll(/\b(?:from|join)\s+([\w.[\]"]+)/gi)) {
    if (!match[1].startsWith('(')) tables.push(match[1].replace(/[[\]"]/g, ''))
  }
  return tables
}

/** The last name part of the first table in FROM, for example `customers` in `dbo.customers`. */
export function firstTable(query: string): string | undefined {
  const table = referencedTables(query)[0]
  return table?.split('.').pop()
}

export function checkSql(query: string): SqlCheck {
  const issues: SqlIssue[] = []
  const clean = stripLiterals(stripComments(query)).trim().replace(/;\s*$/, '')
  const lower = clean.toLowerCase()

  if (!clean) {
    issues.push({ severity: 'error', message: 'Query is empty' })
    return { issues, mode: 'query', tables: [] }
  }
  if (clean.includes(';')) {
    issues.push({ severity: 'error', message: 'Only one statement is allowed' })
  }
  if (!/^(select|with)\b/.test(lower)) {
    issues.push({ severity: 'error', message: 'The query must start with SELECT or WITH' })
  }
  for (const word of FORBIDDEN) {
    if (new RegExp(`\\b${word}\\b`).test(lower)) {
      issues.push({ severity: 'error', message: `"${word.toUpperCase()}" is not allowed in a read-only query` })
    }
  }
  if (/\bselect\b[\s\S]*\binto\b\s+[#\w[]/.test(lower)) {
    issues.push({ severity: 'error', message: 'SELECT ... INTO is not allowed' })
  }
  if (/\border\s+by\b[^)]*$/.test(lower)) {
    issues.push({ severity: 'warning', message: 'A top-level ORDER BY is removed before the run' })
  }
  if (/\bselect\s+(top\s+\S+\s+)?\*/.test(lower)) {
    issues.push({ severity: 'warning', message: 'SELECT * changes the output when the source table changes; list the columns' })
  }

  const tables = referencedTables(query)
  const simple = tables.length === 1 && !/\b(join|group\s+by|union|with|distinct|having|over)\b/.test(lower)
  return { issues, mode: simple ? 'table' : 'query', tables }
}

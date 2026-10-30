import { CircleAlertIcon, CircleCheckIcon, LoaderIcon, PlusIcon, ShieldCheckIcon, TableIcon, TriangleAlertIcon } from 'lucide-react'
import { Link } from 'react-router'
import type { Connection, QueryPreview, SqlValidation } from '@/api/types'
import { CodeEditor } from '@/components/code-editor'
import { Field } from '@/components/field'
import { ParamFields } from '@/components/param-fields'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { findSourceTemplate, withDefaults } from '@/lib/templates'
import { prefixed, type JobDraft } from '@/pages/jobs/job-draft'

interface SourceStepProps {
  draft: JobDraft
  update: (patch: Partial<JobDraft>) => void
  errors: Record<string, string>
  connections: Connection[]
  validation: SqlValidation | null
  validating: boolean
  onValidate: () => void
  preview: QueryPreview | null
  previewing: boolean
  previewError: string | null
  onPreview: () => void
}

export function SourceStep(props: SourceStepProps) {
  const { draft, update, errors, connections, validation, validating, onValidate } = props
  const template = findSourceTemplate(draft.connectionTemplate)
  const items = connections.map((c) => ({ label: c.name, value: c.name }))

  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Query</CardTitle>
          <CardDescription>
            {template?.connector === 'kafka'
              ? "Flink SQL over the table landing: one row per API record, its JSON in the column payload (ADR-0015)."
              : "One read-only SELECT in the source's own dialect. Joins and CTEs are allowed."}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <Field label="Connection" htmlFor="job-connection" required error={errors.connection}>
            <div className="flex gap-2">
              <Select
                items={items}
                value={draft.connection || null}
                onValueChange={(value) => {
                  const connection = connections.find((c) => c.name === value)
                  if (!connection) return
                  update({
                    connection: connection.name,
                    connectionTemplate: connection.template,
                    read: withDefaults(findSourceTemplate(connection.template)?.read_params ?? {}),
                  })
                }}
              >
                <SelectTrigger id="job-connection" className="w-full sm:w-80">
                  <SelectValue placeholder="Select a connection" />
                </SelectTrigger>
                <SelectContent>
                  {connections.map((c) => (
                    <SelectItem key={c.name} value={c.name}>
                      {c.name}
                      <span className="text-xs text-muted-foreground">{c.template}</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button variant="ghost" nativeButton={false} render={<Link to="/connections/new" />}>
                <PlusIcon /> New
              </Button>
            </div>
          </Field>

          <Field label="SQL" required error={errors.query}>
            <CodeEditor language="sql" value={draft.query} onChange={(query) => update({ query })} minHeight="14rem" />
          </Field>

          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" onClick={onValidate} disabled={!draft.connection || !draft.query.trim() || validating}>
              {validating ? <LoaderIcon className="animate-spin" /> : <ShieldCheckIcon />} Validate
            </Button>
            <Button variant="outline" onClick={props.onPreview} disabled={!draft.connection || !draft.query.trim() || props.previewing}>
              {props.previewing ? <LoaderIcon className="animate-spin" /> : <TableIcon />} Preview
            </Button>
            {validation && (
              <Badge variant={validation.ok ? 'secondary' : 'destructive'} className="ml-auto">
                {validation.ok ? <CircleCheckIcon /> : <CircleAlertIcon />}
                {validation.ok ? `Valid · ${validation.mode} mode` : 'Not valid'}
              </Badge>
            )}
          </div>

          {!!validation?.issues.length && (
            <ul className="grid gap-1 rounded-lg border p-3 text-sm">
              {validation.issues.map((issue) => (
                <li key={issue.message} className="flex items-start gap-2">
                  {issue.severity === 'error' ? (
                    <CircleAlertIcon className="mt-0.5 size-4 shrink-0 text-destructive" />
                  ) : (
                    <TriangleAlertIcon className="mt-0.5 size-4 shrink-0 text-amber-500" />
                  )}
                  {issue.message}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {(props.preview || props.previewError) && <PreviewCard preview={props.preview} error={props.previewError} />}

      {template && (
        <Card>
          <CardHeader>
            <CardTitle>Read options</CardTitle>
            <CardDescription>
              Optional. A partition column splits the read into parallel ranges; without one the source is read with
              parallelism 1.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ParamFields
              idPrefix="read"
              defs={template.read_params}
              values={draft.read}
              errors={prefixed(errors, 'read.')}
              onChange={(read) => update({ read })}
            />
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function PreviewCard({ preview, error }: { preview: QueryPreview | null; error: string | null }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Preview</CardTitle>
        <CardDescription>{error ? 'The preview failed' : `First ${preview?.rows.length ?? 0} rows`}</CardDescription>
      </CardHeader>
      <CardContent>
        {error ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : (
          preview && (
            <div className="overflow-x-auto rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    {preview.columns.map((c) => (
                      <TableHead key={c.name}>
                        <div>{c.name}</div>
                        <div className="font-mono text-[10px] font-normal text-muted-foreground">{c.type}</div>
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {preview.rows.map((row, i) => (
                    <TableRow key={i}>
                      {row.map((value, j) => (
                        <TableCell key={j} className="font-mono text-xs">
                          {String(value)}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )
        )}
      </CardContent>
    </Card>
  )
}

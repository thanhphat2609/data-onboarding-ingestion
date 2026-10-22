import { FolderTreeIcon } from 'lucide-react'
import { Field } from '@/components/field'
import { ParamFields } from '@/components/param-fields'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { findSinkTemplate, renderTemplate, sinkTemplates, templateRef, withDefaults } from '@/lib/templates'
import { prefixed, type JobDraft } from '@/pages/jobs/job-draft'

interface SinkStepProps {
  draft: JobDraft
  update: (patch: Partial<JobDraft>) => void
  errors: Record<string, string>
}

export function SinkStep({ draft, update, errors }: SinkStepProps) {
  const template = findSinkTemplate(draft.sinkTemplate)
  const items = sinkTemplates.map((t) => ({ label: `${t.name} (v${t.version})`, value: templateRef(t) }))

  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Destination</CardTitle>
          <CardDescription>Every table is partitioned by ingest_date; a re-run replaces only that day.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <Field label="Sink template" htmlFor="sink-template">
            <Select
              items={items}
              value={draft.sinkTemplate}
              onValueChange={(v) => {
                if (!v) return
                update({ sinkTemplate: v, sinkParams: withDefaults(findSinkTemplate(v)?.params ?? {}) })
              }}
            >
              <SelectTrigger id="sink-template" className="w-full sm:w-80">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {items.map((t) => (
                  <SelectItem key={t.value} value={t.value}>
                    {t.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          {template && (
            <ParamFields
              idPrefix="sink"
              defs={template.params}
              values={draft.sinkParams}
              errors={prefixed(errors, 'sink.')}
              onChange={(sinkParams) => update({ sinkParams })}
            />
          )}
        </CardContent>
      </Card>

      {template && (
        <Card>
          <CardHeader>
            <CardTitle>Lake layout</CardTitle>
            <CardDescription>
              {template.format} · published by <code className="font-mono">{template.publish}</code> after the row
              count is verified
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-start gap-2 rounded-lg bg-muted p-3 font-mono text-xs break-all">
              <FolderTreeIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              <span>
                {renderTemplate(template.uri, draft.sinkParams)}/
                <span className="text-muted-foreground">ingest_date=YYYY-MM-DD/part-*.parquet</span>
              </span>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

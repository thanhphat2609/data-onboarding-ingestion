import { CircleCheckIcon, CircleXIcon, LoaderIcon, PlugIcon } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import { api } from '@/api/client'
import { useConnection, useConnections, useSaveConnection } from '@/api/hooks'
import type { Connection, ConnectionTestResult } from '@/api/types'
import { Field } from '@/components/field'
import { PageHeader } from '@/components/page-header'
import { ParamFields } from '@/components/param-fields'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { YamlPanel } from '@/components/yaml-panel'
import { nameError } from '@/lib/naming'
import {
  findSourceTemplate,
  sourceTemplates,
  templateRef,
  validateParams,
  withDefaults,
  withoutDefaults,
} from '@/lib/templates'
import { connectionToYaml } from '@/lib/yaml'

const RUN_WINDOW = /^([01][0-9]|2[0-3]):[0-5][0-9]-([01][0-9]|2[0-3]):[0-5][0-9]$/

export function ConnectionFormPage() {
  const { name } = useParams()
  const existing = useConnection(name)
  if (name && existing.isPending) return <Skeleton className="h-96 w-full" />
  if (name && existing.isError) return <p className="text-destructive">{existing.error.message}</p>
  return <ConnectionForm key={name ?? 'new'} initial={existing.data} />
}

function ConnectionForm({ initial }: { initial?: Connection }) {
  const isNew = !initial
  const navigate = useNavigate()
  const connections = useConnections()
  const saveMutation = useSaveConnection()

  const [name, setName] = useState(initial?.name ?? '')
  const [owner, setOwner] = useState(initial?.owner ?? 'de-team')
  const [template, setTemplate] = useState(initial?.template ?? templateRef(sourceTemplates[0]))
  const tpl = findSourceTemplate(template)
  const [params, setParams] = useState<Record<string, unknown>>(() =>
    withDefaults(tpl?.connection_params ?? {}, initial?.params),
  )
  const [maxRuns, setMaxRuns] = useState(String(initial?.limits?.max_concurrent_runs ?? 2))
  const [maxPartitions, setMaxPartitions] = useState(String(initial?.limits?.max_partition_num ?? ''))
  const [runWindow, setRunWindow] = useState(initial?.limits?.run_window ?? '')
  const [showErrors, setShowErrors] = useState(false)
  const [test, setTest] = useState<ConnectionTestResult | 'running' | null>(null)

  const connection: Connection = useMemo(
    () => ({
      kind: 'Connection',
      name,
      template,
      owner,
      params: withoutDefaults(tpl?.connection_params ?? {}, params),
      limits: {
        max_concurrent_runs: maxRuns === '' || maxRuns === '2' ? undefined : Number(maxRuns),
        max_partition_num: maxPartitions === '' ? undefined : Number(maxPartitions),
        run_window: runWindow || undefined,
      },
    }),
    [name, template, owner, tpl, params, maxRuns, maxPartitions, runWindow],
  )

  const errors = {
    name: nameError(name, connections.data?.map((c) => c.name) ?? [], isNew) ?? undefined,
    owner: owner.trim() ? undefined : 'Required',
    maxRuns: /^([1-9]|1[0-6])$/.test(maxRuns) ? undefined : 'Between 1 and 16',
    maxPartitions: maxPartitions === '' || /^([1-9]|[12][0-9]|3[0-2])$/.test(maxPartitions) ? undefined : 'Between 1 and 32',
    runWindow: runWindow === '' || RUN_WINDOW.test(runWindow) ? undefined : 'Format HH:MM-HH:MM',
  }
  const paramErrors = validateParams(tpl?.connection_params ?? {}, params)
  const valid = !Object.values(errors).some(Boolean) && !Object.keys(paramErrors).length
  const visible = (e?: string) => (showErrors || !isNew ? e : undefined)

  const runTest = async () => {
    setTest('running')
    try {
      setTest(await api.testConnection({ ...connection, params }))
    } catch (e) {
      setTest({ ok: false, message: (e as Error).message })
    }
  }

  const save = () => {
    setShowErrors(true)
    if (!valid) return
    saveMutation.mutate(
      { connection, isNew },
      {
        onSuccess: () => {
          toast.success(`Saved pipelines/connections/${name}.yaml`)
          navigate('/connections')
        },
        onError: (e) => toast.error('Could not save', { description: e.message }),
      },
    )
  }

  const templateItems = sourceTemplates.map((t) => ({ label: `${t.name} (v${t.version})`, value: templateRef(t) }))

  return (
    <>
      <PageHeader
        title={isNew ? 'New connection' : name}
        description="Onboard a source once; jobs then read from it with a read-only login."
        actions={
          <>
            <Button variant="outline" onClick={() => navigate('/connections')}>
              Cancel
            </Button>
            <Button onClick={save} disabled={saveMutation.isPending}>
              Save connection
            </Button>
          </>
        }
      />

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_400px]">
        <div className="grid gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Details</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <Field
                label="Name"
                htmlFor="conn-name"
                required
                error={visible(errors.name)}
                description={isNew ? 'Saved as pipelines/connections/<name>.yaml; cannot change later' : 'Names cannot change'}
              >
                <Input
                  id="conn-name"
                  value={name}
                  disabled={!isNew}
                  placeholder="crm-sqlserver-nonprod"
                  onChange={(e) => setName(e.target.value.trim())}
                />
              </Field>
              <Field label="Owner" htmlFor="conn-owner" required error={visible(errors.owner)}>
                <Input id="conn-owner" value={owner} onChange={(e) => setOwner(e.target.value)} />
              </Field>
              <Field label="Source template" htmlFor="conn-template" className="sm:col-span-2">
                <Select
                  items={templateItems}
                  value={template}
                  onValueChange={(v) => {
                    if (!v) return
                    setTemplate(v)
                    setParams(withDefaults(findSourceTemplate(v)?.connection_params ?? {}))
                  }}
                >
                  <SelectTrigger id="conn-template" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {templateItems.map((t) => (
                      <SelectItem key={t.value} value={t.value}>
                        {t.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Connection</CardTitle>
              <CardDescription>Fields come from the template; secrets are references, never values.</CardDescription>
            </CardHeader>
            <CardContent>
              {tpl && (
                <ParamFields
                  idPrefix="conn"
                  defs={tpl.connection_params}
                  values={params}
                  errors={showErrors || !isNew ? paramErrors : {}}
                  onChange={(v) => {
                    setParams(v)
                    setTest(null)
                  }}
                />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Limits</CardTitle>
              <CardDescription>Protect the source from too many or too wide reads.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-3">
              <Field
                label="Max concurrent runs"
                htmlFor="conn-max-runs"
                error={visible(errors.maxRuns)}
                description={
                  <>
                    Size of Airflow pool <code className="font-mono">conn__{name || '<name>'}</code>
                  </>
                }
              >
                <Input id="conn-max-runs" type="number" min={1} max={16} value={maxRuns} onChange={(e) => setMaxRuns(e.target.value)} />
              </Field>
              <Field label="Max partitions per job" htmlFor="conn-max-partitions" error={visible(errors.maxPartitions)} description="Caps partition_num">
                <Input
                  id="conn-max-partitions"
                  type="number"
                  min={1}
                  max={32}
                  value={maxPartitions}
                  placeholder="No cap"
                  onChange={(e) => setMaxPartitions(e.target.value)}
                />
              </Field>
              <Field label="Run window" htmlFor="conn-window" error={visible(errors.runWindow)} description="Local time, empty for any time">
                <Input id="conn-window" value={runWindow} placeholder="19:00-06:00" onChange={(e) => setRunWindow(e.target.value)} />
              </Field>
            </CardContent>
          </Card>
        </div>

        <div className="grid gap-4 lg:sticky lg:top-20">
          <Card>
            <CardHeader>
              <CardTitle>Test connection</CardTitle>
              <CardDescription>Opens a connection with these settings and closes it.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3">
              <Button variant="outline" onClick={runTest} disabled={test === 'running'}>
                {test === 'running' ? <LoaderIcon className="animate-spin" /> : <PlugIcon />}
                Test connection
              </Button>
              {test && test !== 'running' && (
                <Alert variant={test.ok ? 'default' : 'destructive'}>
                  {test.ok ? <CircleCheckIcon className="text-emerald-600" /> : <CircleXIcon />}
                  <AlertTitle>{test.ok ? 'Connection succeeded' : 'Connection failed'}</AlertTitle>
                  <AlertDescription>
                    {test.message}
                    {test.latencyMs !== undefined && ` · ${test.latencyMs} ms`}
                  </AlertDescription>
                </Alert>
              )}
            </CardContent>
          </Card>
          <YamlPanel path={`pipelines/connections/${name || '<name>'}.yaml`} yaml={connectionToYaml(connection)} maxHeight="24rem" />
        </div>
      </div>
    </>
  )
}

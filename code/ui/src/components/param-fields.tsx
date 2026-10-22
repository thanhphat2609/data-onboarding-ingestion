import { cn } from 'cn'
import { KeyRoundIcon } from 'lucide-react'
import { Field } from '@/components/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { humanize, type ParamDef, type ParamDefs, type ParamErrors } from '@/lib/templates'

interface ParamFieldsProps {
  /** Parameter declarations from a template, for example `connection_params`. */
  defs: ParamDefs
  values: Record<string, unknown>
  errors?: ParamErrors
  onChange: (values: Record<string, unknown>) => void
  idPrefix: string
  className?: string
}

/** Renders a form for template parameters, so a new template needs no frontend change. */
export function ParamFields({ defs, values, errors = {}, onChange, idPrefix, className }: ParamFieldsProps) {
  const set = (key: string, value: unknown) => onChange({ ...values, [key]: value })

  return (
    <div className={cn('grid items-start gap-4 sm:grid-cols-2', className)}>
      {Object.entries(defs).map(([key, def]) => {
        const id = `${idPrefix}-${key}`
        if (def.type === 'bool') {
          return (
            <div key={key} className="flex items-start gap-3 rounded-lg border p-3 sm:mt-6">
              <Switch id={id} checked={Boolean(values[key])} onCheckedChange={(checked) => set(key, checked)} />
              <div className="grid gap-0.5">
                <label htmlFor={id} className="text-sm font-medium leading-none">
                  {humanize(key)}
                </label>
                {def.description && <p className="text-xs text-muted-foreground">{def.description}</p>}
              </div>
            </div>
          )
        }
        return (
          <Field
            key={key}
            label={humanize(key)}
            htmlFor={id}
            description={def.description}
            error={errors[key]}
            required={def.required}
          >
            <ParamInput id={id} def={def} value={values[key]} invalid={!!errors[key]} onChange={(v) => set(key, v)} />
          </Field>
        )
      })}
    </div>
  )
}

interface ParamInputProps {
  id: string
  def: ParamDef
  value: unknown
  invalid: boolean
  onChange: (value: unknown) => void
}

function ParamInput({ id, def, value, invalid, onChange }: ParamInputProps) {
  if (def.type === 'enum') {
    const items = (def.values ?? []).map((v) => ({ label: v, value: v }))
    return (
      <Select items={items} value={(value as string) ?? null} onValueChange={(v) => onChange(v ?? undefined)}>
        <SelectTrigger id={id} className="w-full" aria-invalid={invalid}>
          <SelectValue placeholder="Select…" />
        </SelectTrigger>
        <SelectContent>
          {items.map((item) => (
            <SelectItem key={item.value} value={item.value}>
              {item.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    )
  }

  if (def.type === 'int') {
    return (
      <Input
        id={id}
        type="number"
        min={def.min}
        max={def.max}
        value={value === undefined ? '' : String(value)}
        aria-invalid={invalid}
        onChange={(e) => onChange(e.target.value === '' ? undefined : Number(e.target.value))}
      />
    )
  }

  if (def.type === 'list') {
    return (
      <Input
        id={id}
        placeholder="comma, separated"
        value={Array.isArray(value) ? value.join(', ') : ''}
        aria-invalid={invalid}
        onChange={(e) =>
          onChange(
            e.target.value
              .split(',')
              .map((s) => s.trim())
              .filter(Boolean),
          )
        }
      />
    )
  }

  const secret = def.type === 'secret_ref'
  return (
    <div className="relative">
      {secret && (
        <KeyRoundIcon className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
      )}
      <Input
        id={id}
        className={cn(secret && 'pl-8 font-mono')}
        placeholder={secret ? 'env://MY_SECRET' : def.type === 'duration' ? '30m' : undefined}
        value={(value as string) ?? ''}
        aria-invalid={invalid}
        autoComplete="off"
        spellCheck={false}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}

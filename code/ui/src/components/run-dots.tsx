import { cn } from 'cn'
import type { RunState, RunSummary } from '@/api/types'

const DOT: Record<RunState, string> = {
  success: 'bg-emerald-500',
  failed: 'bg-red-500',
  running: 'bg-sky-500 animate-pulse',
  queued: 'bg-muted-foreground/40',
}

const LABEL: Record<RunState, string> = {
  success: 'Succeeded',
  failed: 'Failed',
  running: 'Running',
  queued: 'Queued',
}

/** The most recent runs, oldest first, as colored dots with the latest state as text. */
export function RunDots({ runs }: { runs: RunSummary[] }) {
  if (!runs.length) return <span className="text-xs text-muted-foreground">No runs yet</span>
  const last = runs[runs.length - 1]
  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-1">
        {runs.map((run) => (
          <span
            key={run.runId}
            title={`${run.ingestDate} · ${LABEL[run.state]} · ${run.trigger}`}
            className={cn('size-2.5 rounded-full', DOT[run.state])}
          />
        ))}
      </div>
      <span className="text-xs text-muted-foreground">{LABEL[last.state]}</span>
    </div>
  )
}

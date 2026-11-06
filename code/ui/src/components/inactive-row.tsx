import type { ReactNode } from 'react'
import type { PullRequestRef } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

/** The Status column of a list: green for what is merged, blue for a save whose pull request is still open. */
export function StatusBadge({ active }: { active: boolean }) {
  return active ? (
    <Badge className="border-transparent bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
      Active
    </Badge>
  ) : (
    <Badge className="border-transparent bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300">Inactive</Badge>
  )
}

/** What hovering an inactive row says. */
function inactiveMessage(kind: 'connection' | 'job', pull: PullRequestRef) {
  return `Not active yet: pull request #${pull.number} hasn't been merged. This ${kind} becomes active about a minute after the merge; until then it can't be opened or used.`
}

/**
 * A table row for a connection or job whose pull request is not merged yet (ADR-0018): listed, with Status
 * "Inactive", so nobody saves it twice, but nothing in it is a link or a button. Hovering it says why.
 */
export function InactiveRow({
  kind,
  pull,
  children,
}: {
  kind: 'connection' | 'job'
  pull: PullRequestRef
  children: ReactNode
}) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={<TableRow className="cursor-not-allowed select-none bg-muted/40 hover:bg-muted/40" aria-disabled />}
      >
        {children}
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs">
        {inactiveMessage(kind, pull)}
      </TooltipContent>
    </Tooltip>
  )
}

/** Content of a cell of an inactive row: faded, and not clickable. The Status cell stays readable. */
export function Dimmed({ children }: { children: ReactNode }) {
  return <div className="pointer-events-none opacity-50">{children}</div>
}

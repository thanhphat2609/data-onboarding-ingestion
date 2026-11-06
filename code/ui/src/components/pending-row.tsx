import type { ReactNode } from 'react'
import type { PullRequestRef } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

/** Blue badge for a save whose pull request is still open. */
export function PendingBadge() {
  return (
    <Badge className="border-transparent bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300">Pending merge</Badge>
  )
}

/**
 * A table row for a connection or job whose pull request is not merged yet (ADR-0017): visible so nobody saves it
 * twice, but blurred and inert. Nothing in it is a link or a button; hovering it says why.
 */
export function PendingRow({
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
        render={<TableRow className="cursor-not-allowed select-none bg-sky-50/70 hover:bg-sky-50/70 dark:bg-sky-950/20" />}
      >
        {children}
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs">
        This {kind} is waiting for its pull request #{pull.number} to be merged. It can be used after the merge, about a
        minute later.
      </TooltipContent>
    </Tooltip>
  )
}

/** Content of a cell of a pending row: blurred and faded. */
export function Blurred({ children }: { children: ReactNode }) {
  return <div className="pointer-events-none opacity-60 blur-[1.5px]">{children}</div>
}

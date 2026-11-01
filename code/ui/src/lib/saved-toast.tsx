import { toast } from 'sonner'
import type { PullRequestRef } from '@/api/types'

/** Tells the user what a save did: with a pull request, where to review it (ADR-0017). */
export function toastSaved(what: string, pullRequest?: PullRequestRef, description?: string) {
  if (!pullRequest) {
    toast.success(`Saved ${what}`, { description })
    return
  }
  toast.success(`Pull request #${pullRequest.number} opened for ${what}`, {
    description: description ?? 'Review and merge it in the orchestration repository.',
    action: { label: 'Open', onClick: () => window.open(pullRequest.url, '_blank', 'noreferrer') },
    duration: 15000,
  })
}

import { lazy, Suspense } from 'react'
import type { CodeEditorProps } from '@/components/code-mirror-editor'
import { Skeleton } from '@/components/ui/skeleton'

// CodeMirror is the largest dependency; load it only on pages that show an editor.
const CodeMirrorEditor = lazy(() => import('@/components/code-mirror-editor'))

export function CodeEditor(props: CodeEditorProps) {
  return (
    <Suspense fallback={<Skeleton className="w-full" style={{ height: props.minHeight ?? '12rem' }} />}>
      <CodeMirrorEditor {...props} />
    </Suspense>
  )
}

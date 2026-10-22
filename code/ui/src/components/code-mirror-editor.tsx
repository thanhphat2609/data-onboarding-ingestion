import { MSSQL, sql } from '@codemirror/lang-sql'
import { yaml } from '@codemirror/lang-yaml'
import { Compartment, EditorState } from '@codemirror/state'
import { oneDark } from '@codemirror/theme-one-dark'
import { EditorView, basicSetup } from 'codemirror'
import { cn } from 'cn'
import { useEffect, useRef } from 'react'
import { useTheme } from '@/components/theme-provider'

export interface CodeEditorProps {
  value: string
  onChange?: (value: string) => void
  language: 'sql' | 'yaml'
  readOnly?: boolean
  minHeight?: string
  maxHeight?: string
  className?: string
}

export default function CodeMirrorEditor({
  value,
  onChange,
  language,
  readOnly = false,
  minHeight = '12rem',
  maxHeight,
  className,
}: CodeEditorProps) {
  const host = useRef<HTMLDivElement>(null)
  const view = useRef<EditorView | null>(null)
  const themeSlot = useRef(new Compartment())
  const onChangeRef = useRef(onChange)
  const { resolvedTheme } = useTheme()

  useEffect(() => {
    onChangeRef.current = onChange
  })

  // The editor is created once per language/read-only combination; later value changes are dispatched.
  useEffect(() => {
    const editor = new EditorView({
      parent: host.current!,
      state: EditorState.create({
        doc: value,
        extensions: [
          basicSetup,
          language === 'sql' ? sql({ dialect: MSSQL, upperCaseKeywords: true }) : yaml(),
          EditorState.readOnly.of(readOnly),
          EditorView.editable.of(!readOnly),
          themeSlot.current.of([]),
          EditorView.theme({
            '&': { fontSize: '13px', backgroundColor: 'transparent' },
            '&.cm-focused': { outline: 'none' },
            '.cm-scroller': { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace', maxHeight: maxHeight ?? 'none' },
            '.cm-content, .cm-gutter': { minHeight },
          }),
          EditorView.updateListener.of((update) => {
            if (update.docChanged) onChangeRef.current?.(update.state.doc.toString())
          }),
        ],
      }),
    })
    view.current = editor
    return () => editor.destroy()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [language, readOnly])

  useEffect(() => {
    const editor = view.current
    if (!editor) return
    const current = editor.state.doc.toString()
    if (current !== value) editor.dispatch({ changes: { from: 0, to: current.length, insert: value } })
  }, [value])

  useEffect(() => {
    view.current?.dispatch({ effects: themeSlot.current.reconfigure(resolvedTheme === 'dark' ? oneDark : []) })
  }, [resolvedTheme, language, readOnly])

  return (
    <div
      ref={host}
      className={cn('overflow-hidden rounded-lg border bg-background dark:bg-[#282c34]', className)}
    />
  )
}

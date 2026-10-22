import { CheckIcon, CopyIcon, DownloadIcon } from 'lucide-react'
import { useState } from 'react'
import { CodeEditor } from '@/components/code-editor'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { downloadText } from '@/lib/yaml'

interface YamlPanelProps {
  path: string
  yaml: string
  maxHeight?: string
}

/** Read-only view of the YAML file that will be saved, with copy and export. */
export function YamlPanel({ path, yaml, maxHeight = '32rem' }: YamlPanelProps) {
  const [copied, setCopied] = useState(false)
  const fileName = path.split('/').pop() ?? 'file.yaml'

  const copy = async () => {
    await navigator.clipboard.writeText(yaml)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>YAML</CardTitle>
        <CardDescription className="font-mono text-xs">{path}</CardDescription>
        <CardAction className="flex gap-1">
          <Button variant="ghost" size="icon-sm" aria-label="Copy YAML" onClick={copy}>
            {copied ? <CheckIcon /> : <CopyIcon />}
          </Button>
          <Button variant="ghost" size="icon-sm" aria-label="Export YAML" onClick={() => downloadText(fileName, yaml)}>
            <DownloadIcon />
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        <CodeEditor language="yaml" value={yaml} readOnly minHeight="8rem" maxHeight={maxHeight} />
      </CardContent>
    </Card>
  )
}

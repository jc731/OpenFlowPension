import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Settings, ChevronDown, ChevronRight } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { systemConfigApi } from '@/lib/api'
import type { SystemConfigEntry } from '@/lib/api'

function groupByKey(entries: SystemConfigEntry[]) {
  const map: Record<string, SystemConfigEntry[]> = {}
  for (const e of entries) {
    if (!map[e.config_key]) map[e.config_key] = []
    map[e.config_key].push(e)
  }
  return map
}

function ConfigValueViewer({ value }: { value: unknown }) {
  return (
    <pre className="bg-muted rounded p-3 text-xs overflow-x-auto max-h-64 whitespace-pre-wrap break-all">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

function ConfigKeyCard({ configKey, entries }: { configKey: string; entries: SystemConfigEntry[] }) {
  const [expanded, setExpanded] = useState(false)
  const active = entries.find(e => !e.superseded_date)
  const historical = entries.filter(e => !!e.superseded_date)

  return (
    <Card>
      <CardHeader className="py-4 cursor-pointer select-none" onClick={() => setExpanded(v => !v)}>
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            {expanded ? <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />}
            <CardTitle className="text-sm font-mono">{configKey}</CardTitle>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {active && <Badge variant="success" className="text-xs">active</Badge>}
            {historical.length > 0 && <Badge variant="secondary" className="text-xs">{historical.length} historical</Badge>}
            {!active && <Badge variant="destructive" className="text-xs">no active row</Badge>}
          </div>
        </div>
        {active && (
          <CardDescription className="text-xs ml-6">
            effective {active.effective_date}
            {active.note && ` · ${active.note}`}
          </CardDescription>
        )}
      </CardHeader>
      {expanded && (
        <CardContent className="pt-0 space-y-3">
          {active && (
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1">Active value (effective {active.effective_date})</p>
              <ConfigValueViewer value={active.config_value} />
            </div>
          )}
          {historical.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1">Historical</p>
              <div className="space-y-2">
                {historical.map(e => (
                  <div key={e.id}>
                    <p className="text-xs text-muted-foreground">effective {e.effective_date} → superseded {e.superseded_date}</p>
                    <ConfigValueViewer value={e.config_value} />
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      )}
    </Card>
  )
}

export default function SystemConfig() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['system-configurations'],
    queryFn: () => systemConfigApi.list(),
  })
  const entries = data?.data ?? []
  const grouped = groupByKey(entries)
  const keys = Object.keys(grouped).sort()

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center gap-3">
        <Settings className="h-5 w-5 text-muted-foreground" />
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">System Configuration</h1>
          <p className="text-sm text-muted-foreground">Fund-level rules stored in system_configurations · click a key to expand</p>
        </div>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && <p className="text-sm text-destructive">Failed to load configurations.</p>}

      {!isLoading && keys.length === 0 && !error && (
        <p className="text-sm text-muted-foreground">No configurations found. Run <code className="bg-muted px-1 rounded">make seed</code> to populate defaults.</p>
      )}

      <div className="grid gap-3">
        {keys.map(k => (
          <ConfigKeyCard key={k} configKey={k} entries={grouped[k]} />
        ))}
      </div>
    </div>
  )
}

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Settings, ChevronDown, ChevronRight, Plus } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Dialog, DialogContent, DialogHeader, DialogFooter,
  DialogTitle, DialogDescription,
} from '@/components/ui/dialog'
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

const EMPTY_FORM = { config_key: '', effective_date: '', config_value: '', note: '' }

function AddConfigDialog({ open, onOpenChange, existingKeys }: {
  open: boolean
  onOpenChange: (v: boolean) => void
  existingKeys: string[]
}) {
  const qc = useQueryClient()
  const [form, setForm] = useState(EMPTY_FORM)
  const [jsonError, setJsonError] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: systemConfigApi.create,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['system-configurations'] })
      toast.success('Configuration row added')
      onOpenChange(false)
      setForm(EMPTY_FORM)
      setJsonError(null)
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail ?? 'Failed to save configuration')
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    let parsed: Record<string, unknown>
    try {
      parsed = JSON.parse(form.config_value)
      setJsonError(null)
    } catch {
      setJsonError('Invalid JSON — fix before saving')
      return
    }
    create.mutate({
      config_key: form.config_key.trim(),
      config_value: parsed,
      effective_date: form.effective_date,
      note: form.note.trim() || undefined,
    })
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) { setForm(EMPTY_FORM); setJsonError(null) } }}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Add Config Value</DialogTitle>
          <DialogDescription>
            Insert a new effective-dated row. The new row supersedes the current active row for the same key.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="text-sm font-medium">Config key</label>
              <Input
                list="config-key-list"
                value={form.config_key}
                onChange={e => setForm(f => ({ ...f, config_key: e.target.value }))}
                placeholder="e.g. service_credit_accrual_rule"
                required
              />
              <datalist id="config-key-list">
                {existingKeys.map(k => <option key={k} value={k} />)}
              </datalist>
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium">Effective date</label>
              <Input
                type="date"
                value={form.effective_date}
                onChange={e => setForm(f => ({ ...f, effective_date: e.target.value }))}
                required
              />
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium">Config value (JSON)</label>
            <textarea
              className="w-full min-h-[160px] rounded-md border border-input bg-background px-3 py-2 text-sm font-mono focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring resize-y"
              value={form.config_value}
              onChange={e => { setForm(f => ({ ...f, config_value: e.target.value })); setJsonError(null) }}
              placeholder={'{\n  "rule": "monthly_floor"\n}'}
              required
            />
            {jsonError && <p className="text-xs text-destructive">{jsonError}</p>}
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium">Note <span className="text-muted-foreground font-normal">(optional)</span></label>
            <Input
              value={form.note}
              onChange={e => setForm(f => ({ ...f, note: e.target.value }))}
              placeholder="Short description of this change"
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? 'Saving…' : 'Save'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export default function SystemConfig() {
  const [dialogOpen, setDialogOpen] = useState(false)
  const { data, isLoading, error } = useQuery({
    queryKey: ['system-configurations'],
    queryFn: () => systemConfigApi.list(),
  })
  const entries = data?.data ?? []
  const grouped = groupByKey(entries)
  const keys = Object.keys(grouped).sort()

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Settings className="h-5 w-5 text-muted-foreground" />
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">System Configuration</h1>
            <p className="text-sm text-muted-foreground">Fund-level rules stored in system_configurations · click a key to expand</p>
          </div>
        </div>
        <Button onClick={() => setDialogOpen(true)}>
          <Plus className="h-4 w-4" /> Add Config Value
        </Button>
      </div>

      <AddConfigDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        existingKeys={keys}
      />

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

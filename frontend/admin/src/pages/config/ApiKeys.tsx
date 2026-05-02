import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { KeyRound, Copy, RotateCcw, XCircle } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { apiKeysApi } from '@/lib/api'
import { formatDate } from '@/lib/utils'

export default function ApiKeys() {
  const qc = useQueryClient()
  const [newKeySecret, setNewKeySecret] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['api-keys'],
    queryFn: () => apiKeysApi.list(),
  })

  const revoke = useMutation({
    mutationFn: (id: string) => apiKeysApi.revoke(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['api-keys'] }); toast.success('Key revoked') },
  })

  const rotate = useMutation({
    mutationFn: (id: string) => apiKeysApi.rotate(id),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['api-keys'] })
      setNewKeySecret(res.data.plaintext_key)
      toast.success('Key rotated — copy the new key now')
    },
  })

  const create = useMutation({
    mutationFn: () => apiKeysApi.create({ name: 'New Key', scopes: ['*'] }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['api-keys'] })
      setNewKeySecret(res.data.plaintext_key)
      toast.success('Key created — copy it now, it won\'t be shown again')
    },
  })

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <KeyRound className="h-5 w-5 text-muted-foreground" />
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">API Keys</h1>
            <p className="text-sm text-muted-foreground">Machine-to-machine access credentials</p>
          </div>
        </div>
        <Button onClick={() => create.mutate()} disabled={create.isPending}>
          <KeyRound className="h-4 w-4" /> Create Key
        </Button>
      </div>

      {/* One-time secret reveal */}
      {newKeySecret && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 space-y-2">
          <p className="text-sm font-medium text-amber-800">Copy this key — it will not be shown again.</p>
          <div className="flex items-center gap-2">
            <code className="flex-1 text-xs bg-white border rounded px-3 py-2 font-mono break-all">{newKeySecret}</code>
            <Button
              variant="outline" size="sm"
              onClick={() => { navigator.clipboard.writeText(newKeySecret); toast.success('Copied') }}
            >
              <Copy className="h-3 w-3" />
            </Button>
          </div>
          <Button variant="ghost" size="sm" onClick={() => setNewKeySecret(null)}>Dismiss</Button>
        </div>
      )}

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Prefix</TableHead>
              <TableHead>Scopes</TableHead>
              <TableHead>Last Used</TableHead>
              <TableHead>Expires</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="w-24" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground py-8">Loading…</TableCell></TableRow>
            )}
            {data?.data.map(k => (
              <TableRow key={k.id}>
                <TableCell className="font-medium">{k.name}</TableCell>
                <TableCell className="font-mono text-xs">{k.key_prefix}…</TableCell>
                <TableCell>
                  <div className="flex gap-1 flex-wrap">
                    {k.scopes.map(s => <Badge key={s} variant="outline" className="text-xs">{s}</Badge>)}
                  </div>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">{formatDate(k.last_used_at)}</TableCell>
                <TableCell className="text-sm text-muted-foreground">{formatDate(k.expires_at)}</TableCell>
                <TableCell>
                  <Badge variant={k.active ? 'success' : 'secondary'}>{k.active ? 'Active' : 'Revoked'}</Badge>
                </TableCell>
                <TableCell>
                  <div className="flex gap-1">
                    <Button
                      variant="ghost" size="icon" title="Rotate"
                      disabled={!k.active || rotate.isPending}
                      onClick={() => rotate.mutate(k.id)}
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost" size="icon" title="Revoke"
                      disabled={!k.active || revoke.isPending}
                      onClick={() => revoke.mutate(k.id)}
                    >
                      <XCircle className="h-3.5 w-3.5 text-destructive" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

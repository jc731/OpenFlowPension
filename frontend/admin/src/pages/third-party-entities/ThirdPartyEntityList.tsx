import { useQuery } from '@tanstack/react-query'
import { Building2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { thirdPartyEntitiesApi } from '@/lib/api'

export default function ThirdPartyEntityList() {
  const { data, isLoading } = useQuery({
    queryKey: ['third-party-entities'],
    queryFn: () => thirdPartyEntitiesApi.list(false),
  })
  const entities = data?.data ?? []

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center gap-3">
        <Building2 className="h-5 w-5 text-muted-foreground" />
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Third-Party Entities</h1>
          <p className="text-sm text-muted-foreground">Payee organizations (unions, insurers, court orders)</p>
        </div>
      </div>

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>EIN</TableHead>
              <TableHead>Contact</TableHead>
              <TableHead>ACH</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground py-8">Loading…</TableCell></TableRow>
            )}
            {!isLoading && entities.length === 0 && (
              <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground py-8">No third-party entities on record.</TableCell></TableRow>
            )}
            {entities.map(e => (
              <TableRow key={e.id}>
                <TableCell className="font-medium">{e.name}</TableCell>
                <TableCell>
                  <Badge variant="secondary" className="capitalize">{e.entity_type.replace('_', ' ')}</Badge>
                </TableCell>
                <TableCell className="font-mono text-xs">{e.ein ?? '—'}</TableCell>
                <TableCell className="text-sm">
                  {e.phone && <p>{e.phone}</p>}
                  {e.email && <p className="text-muted-foreground">{e.email}</p>}
                  {!e.phone && !e.email && <span className="text-muted-foreground">—</span>}
                </TableCell>
                <TableCell className="text-sm">
                  {e.bank_routing_number && e.bank_account_last_four
                    ? <span>…{e.bank_account_last_four}</span>
                    : <span className="text-muted-foreground">—</span>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

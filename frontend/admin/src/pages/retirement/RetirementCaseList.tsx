import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { FileText } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { retirementApi } from '@/lib/api'
import { formatDate, formatCurrency } from '@/lib/utils'

const statusVariant: Record<string, 'default' | 'secondary' | 'success' | 'warning' | 'destructive'> = {
  draft: 'secondary', approved: 'warning', active: 'success', cancelled: 'destructive',
}

export default function RetirementCaseList() {
  const { data, isLoading } = useQuery({
    queryKey: ['retirement-cases'],
    queryFn: () => retirementApi.list(),
  })

  const open = data?.data.filter(c => c.status !== 'cancelled') ?? []
  const pending = open.filter(c => c.status === 'draft' || c.status === 'approved')

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center gap-3">
        <FileText className="h-5 w-5 text-muted-foreground" />
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Retirement Cases</h1>
          <p className="text-sm text-muted-foreground">
            {pending.length} pending action · {open.length} total open
          </p>
        </div>
      </div>

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Case ID</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Retirement Date</TableHead>
              <TableHead>Option</TableHead>
              <TableHead>Monthly Annuity</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="w-16" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground py-8">Loading…</TableCell></TableRow>
            )}
            {!isLoading && !data?.data.length && (
              <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground py-8">No retirement cases on file.</TableCell></TableRow>
            )}
            {data?.data.map(c => (
              <TableRow key={c.id}>
                <TableCell className="font-mono text-xs">{c.id.slice(0, 8)}…</TableCell>
                <TableCell><Badge variant={statusVariant[c.status]}>{c.status}</Badge></TableCell>
                <TableCell>{formatDate(c.retirement_date)}</TableCell>
                <TableCell className="capitalize text-sm">{c.benefit_option_type.replace(/_/g, ' ')}</TableCell>
                <TableCell>{c.final_monthly_annuity ? formatCurrency(c.final_monthly_annuity) : '—'}</TableCell>
                <TableCell className="text-sm text-muted-foreground">{formatDate(c.created_at)}</TableCell>
                <TableCell>
                  <Button variant="ghost" size="sm" asChild>
                    <Link to={`/retirement/${c.id}`}>View</Link>
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

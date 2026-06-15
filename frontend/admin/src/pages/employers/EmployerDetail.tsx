import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { employersApi, billingApi } from '@/lib/api'
import { formatDate, formatCurrency } from '@/lib/utils'

const invoiceStatusVariant: Record<string, 'default' | 'secondary' | 'success' | 'warning' | 'destructive'> = {
  draft: 'secondary',
  issued: 'warning',
  paid: 'success',
  overdue: 'destructive',
  voided: 'secondary',
  partial: 'warning',
}

export default function EmployerDetail() {
  const { id } = useParams<{ id: string }>()

  const { data: employer, isLoading } = useQuery({
    queryKey: ['employer', id],
    queryFn: () => employersApi.get(id!),
    enabled: !!id,
  })

  if (isLoading) return <div className="p-6 text-muted-foreground">Loading…</div>
  if (!employer) return <div className="p-6 text-muted-foreground">Employer not found.</div>

  const e = employer.data

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" asChild>
          <Link to="/employers"><ArrowLeft className="h-4 w-4" /></Link>
        </Button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold">{e.name}</h1>
            {!e.active && <Badge variant="secondary">Inactive</Badge>}
          </div>
          <p className="text-sm text-muted-foreground font-mono">{e.employer_code} · {e.employer_type}</p>
        </div>
      </div>

      <Tabs defaultValue="billing">
        <TabsList>
          <TabsTrigger value="billing">Billing</TabsTrigger>
          <TabsTrigger value="rates">Contribution Rates</TabsTrigger>
        </TabsList>

        {/* ── Billing / Invoices ── */}
        <TabsContent value="billing" className="mt-4">
          <BillingTab employerId={e.id} />
        </TabsContent>

        {/* ── Rates ── */}
        <TabsContent value="rates" className="mt-4">
          <RatesTab employerId={e.id} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

function BillingTab({ employerId }: { employerId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['employer-invoices', employerId],
    queryFn: () => billingApi.invoices(employerId),
  })
  const invoices = data?.data ?? []

  const totalDue = invoices.filter(i => i.status !== 'voided' && i.status !== 'paid')
    .reduce((sum, i) => sum + (i.amount_due - i.amount_paid), 0)

  return (
    <div className="space-y-4">
      {invoices.some(i => i.status !== 'voided' && i.status !== 'paid') && (
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground">Outstanding Balance</p>
            <p className="text-2xl font-bold text-destructive mt-1">{formatCurrency(totalDue.toFixed(2))}</p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader><CardTitle className="text-base">Invoices</CardTitle></CardHeader>
        <CardContent>
          {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
          {!isLoading && invoices.length === 0 && (
            <p className="text-sm text-muted-foreground">No invoices on record.</p>
          )}
          {invoices.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Type</TableHead>
                  <TableHead>Period</TableHead>
                  <TableHead>Due Date</TableHead>
                  <TableHead>Amount Due</TableHead>
                  <TableHead>Paid</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {invoices.map(inv => (
                  <TableRow key={inv.id}>
                    <TableCell className="capitalize font-medium">{inv.invoice_type.replace('_', ' ')}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {inv.period_start ? `${formatDate(inv.period_start)} – ${formatDate(inv.period_end)}` : '—'}
                    </TableCell>
                    <TableCell className="text-sm">{formatDate(inv.due_date)}</TableCell>
                    <TableCell>{formatCurrency(inv.amount_due.toFixed(2))}</TableCell>
                    <TableCell>{formatCurrency(inv.amount_paid.toFixed(2))}</TableCell>
                    <TableCell>
                      <Badge variant={invoiceStatusVariant[inv.status] ?? 'secondary'}>{inv.status}</Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function RatesTab({ employerId }: { employerId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['billing-rates', employerId],
    queryFn: () => billingApi.rates(employerId),
  })
  const rates = data?.data ?? []

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Contribution Rates</CardTitle></CardHeader>
      <CardContent>
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {!isLoading && rates.length === 0 && (
          <p className="text-sm text-muted-foreground">No rates configured for this employer (uses fund defaults).</p>
        )}
        {rates.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Employment Type</TableHead>
                <TableHead>Employee Rate</TableHead>
                <TableHead>Employer Rate</TableHead>
                <TableHead>Effective</TableHead>
                <TableHead>End Date</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rates.map(r => (
                <TableRow key={r.id} className={r.end_date ? 'opacity-60' : ''}>
                  <TableCell className="capitalize">{r.employment_type?.replace('_', ' ') ?? 'All types'}</TableCell>
                  <TableCell>{(r.employee_rate * 100).toFixed(2)}%</TableCell>
                  <TableCell>{(r.employer_rate * 100).toFixed(2)}%</TableCell>
                  <TableCell className="text-sm">{formatDate(r.effective_date)}</TableCell>
                  <TableCell className="text-sm">{r.end_date ? formatDate(r.end_date) : <span className="text-xs text-success">Active</span>}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

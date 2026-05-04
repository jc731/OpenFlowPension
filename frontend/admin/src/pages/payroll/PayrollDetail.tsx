import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, CheckCircle2, XCircle, SkipForward, Clock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { payrollApi, employersApi, type PayrollReportRow } from '@/lib/api'
import { formatDate, formatCurrency } from '@/lib/utils'

const rowStatusConfig: Record<PayrollReportRow['status'], { label: string; variant: 'success' | 'destructive' | 'secondary' | 'warning'; icon: React.ElementType }> = {
  applied:  { label: 'Applied',    variant: 'success',     icon: CheckCircle2 },
  error:    { label: 'Error',      variant: 'destructive', icon: XCircle },
  skipped:  { label: 'Skipped',    variant: 'secondary',   icon: SkipForward },
  pending:  { label: 'Pending',    variant: 'warning',     icon: Clock },
}

const reportStatusVariant: Record<string, 'default' | 'secondary' | 'success' | 'warning' | 'destructive'> = {
  pending: 'secondary', processing: 'warning', completed: 'success', failed: 'destructive',
}

export default function PayrollDetail() {
  const { id } = useParams<{ id: string }>()

  const { data: reportRes, isLoading } = useQuery({
    queryKey: ['payroll-report', id],
    queryFn: () => payrollApi.get(id!),
    enabled: !!id,
  })

  const { data: employers } = useQuery({
    queryKey: ['employers'],
    queryFn: () => employersApi.list(),
  })

  if (isLoading) return <div className="p-6 text-muted-foreground">Loading…</div>
  if (!reportRes) return <div className="p-6 text-muted-foreground">Report not found.</div>

  const r = reportRes.data
  const employer = employers?.data.find(e => e.id === r.employer_id)
  const rows = r.rows ?? []
  const errors = rows.filter(row => row.status === 'error')

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" asChild>
          <Link to="/payroll"><ArrowLeft className="h-4 w-4" /></Link>
        </Button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold">Payroll Report</h1>
            <Badge variant={reportStatusVariant[r.status] ?? 'secondary'}>{r.status}</Badge>
            <span className="text-sm text-muted-foreground font-mono">{r.id.slice(0, 8)}…</span>
          </div>
          <p className="text-sm text-muted-foreground">
            {employer?.name ?? 'Unknown employer'} · {r.source_format.toUpperCase()}
            {r.source_filename && ` · ${r.source_filename}`}
            {' · '}{formatDate(r.created_at)}
          </p>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Total Rows', value: r.row_count, color: '' },
          { label: 'Applied', value: r.processed_count, color: 'text-emerald-700' },
          { label: 'Errors', value: r.error_count, color: r.error_count > 0 ? 'text-destructive' : '' },
          { label: 'Skipped', value: r.skipped_count, color: 'text-muted-foreground' },
        ].map(({ label, value, color }) => (
          <Card key={label}>
            <CardContent className="pt-4">
              <p className="text-xs text-muted-foreground">{label}</p>
              <p className={`text-2xl font-bold mt-1 ${color}`}>{value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Error summary — shown only when errors exist */}
      {errors.length > 0 && (
        <Card className="border-destructive/50">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm text-destructive flex items-center gap-2">
              <XCircle className="h-4 w-4" /> {errors.length} row{errors.length > 1 ? 's' : ''} failed — no contribution or service credit was posted for these rows
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1.5">
              {errors.map(row => (
                <div key={row.id} className="flex items-start gap-3 text-sm">
                  <code className="text-xs bg-muted px-1.5 py-0.5 rounded shrink-0">{row.member_number}</code>
                  <span className="text-muted-foreground">{row.period_start} – {row.period_end}</span>
                  <span className="text-destructive">{row.error_message}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Row detail table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Row Detail</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Member #</TableHead>
                <TableHead>Period</TableHead>
                <TableHead className="text-right">Gross Earnings</TableHead>
                <TableHead className="text-right">Employee Contrib</TableHead>
                <TableHead className="text-right">Employer Contrib</TableHead>
                <TableHead className="text-right">Days</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Note</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={8} className="text-center text-muted-foreground py-6">
                    Row detail not loaded — rows are returned on individual report fetch.
                  </TableCell>
                </TableRow>
              )}
              {rows.map(row => {
                const cfg = rowStatusConfig[row.status] ?? rowStatusConfig.pending
                const Icon = cfg.icon
                return (
                  <TableRow key={row.id} className={row.status === 'error' ? 'bg-destructive/5' : undefined}>
                    <TableCell className="font-mono text-xs">{row.member_number}</TableCell>
                    <TableCell className="text-sm whitespace-nowrap">
                      {row.period_start}<span className="text-muted-foreground mx-1">→</span>{row.period_end}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm">{formatCurrency(row.gross_earnings)}</TableCell>
                    <TableCell className="text-right font-mono text-sm">{formatCurrency(row.employee_contribution)}</TableCell>
                    <TableCell className="text-right font-mono text-sm">{formatCurrency(row.employer_contribution)}</TableCell>
                    <TableCell className="text-right font-mono text-sm">{row.days_worked}</TableCell>
                    <TableCell>
                      <Badge variant={cfg.variant} className="gap-1">
                        <Icon className="h-3 w-3" />{cfg.label}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground max-w-64 truncate">
                      {row.error_message ?? '—'}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}

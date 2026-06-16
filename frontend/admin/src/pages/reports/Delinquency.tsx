import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { reportsApi, DelinquencyRow } from '@/lib/api'
import { ReportViewer, ColumnDef } from '@/components/reports/ReportViewer'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'

const columns: ColumnDef<DelinquencyRow>[] = [
  { key: 'employer_name', label: 'Employer' },
  { key: 'employer_code', label: 'Code' },
  {
    key: 'invoice_type',
    label: 'Type',
    render: (v) => <span className="capitalize">{String(v).replace('_', ' ')}</span>,
  },
  {
    key: 'invoice_status',
    label: 'Status',
    render: (v) => (
      <Badge variant={v === 'overdue' ? 'destructive' : 'secondary'} className="capitalize">
        {String(v)}
      </Badge>
    ),
  },
  { key: 'due_date', label: 'Due Date' },
  { key: 'days_overdue', label: 'Days Overdue', className: 'text-right' },
  {
    key: 'amount_due',
    label: 'Amount Due',
    className: 'text-right',
    render: (v) => `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2 })}`,
  },
  {
    key: 'amount_paid',
    label: 'Paid',
    className: 'text-right',
    render: (v) => `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2 })}`,
  },
  {
    key: 'outstanding',
    label: 'Outstanding',
    className: 'text-right font-medium text-destructive',
    render: (v) => `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2 })}`,
  },
]

export default function Delinquency() {
  const today = new Date().toISOString().split('T')[0]
  const [asOf, setAsOf] = useState(today)
  const [runAsOf, setRunAsOf] = useState(today)

  const { data, isLoading } = useQuery({
    queryKey: ['reports', 'delinquency', runAsOf],
    queryFn: () => reportsApi.delinquency(runAsOf).then((r) => r.data),
  })

  const fmt = (v: string | number) =>
    `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2 })}`

  const summary = data
    ? [
        { label: 'Employers', value: data.summary.employer_count },
        { label: 'Invoices', value: data.summary.invoice_count },
        { label: 'Total Outstanding', value: fmt(data.summary.total_outstanding) },
      ]
    : []

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end gap-4">
        <div className="space-y-1">
          <Label htmlFor="as-of">As of Date</Label>
          <Input
            id="as-of"
            type="date"
            value={asOf}
            onChange={(e) => setAsOf(e.target.value)}
            className="w-44"
          />
        </div>
        <Button onClick={() => setRunAsOf(asOf)}>Run Report</Button>
      </div>

      <ReportViewer<DelinquencyRow>
        title="Delinquency Report"
        description="Invoices with outstanding balances past their due date."
        columns={columns}
        rows={data?.rows ?? []}
        summary={summary}
        isLoading={isLoading}
        generatedAt={data?.generated_at}
        csvFilename={`delinquency-${runAsOf}.csv`}
        noRowsMessage="No delinquent invoices as of this date."
      />
    </div>
  )
}

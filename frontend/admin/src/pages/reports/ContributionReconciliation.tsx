import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { reportsApi, ContributionReconciliationRow } from '@/lib/api'
import { ReportViewer, ColumnDef } from '@/components/reports/ReportViewer'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const columns: ColumnDef<ContributionReconciliationRow>[] = [
  { key: 'employer_name', label: 'Employer' },
  { key: 'employer_code', label: 'Code' },
  { key: 'record_count', label: 'Records', className: 'text-right' },
  {
    key: 'total_employee_contributions',
    label: 'Employee Contributions',
    className: 'text-right',
    render: (v) => `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2 })}`,
  },
  {
    key: 'total_employer_contributions',
    label: 'Employer Contributions',
    className: 'text-right',
    render: (v) => `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2 })}`,
  },
  {
    key: 'total_contributions',
    label: 'Total',
    className: 'text-right font-medium',
    render: (v) => `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2 })}`,
  },
]

function todayMinus(days: number) {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return d.toISOString().split('T')[0]
}

export default function ContributionReconciliation() {
  const [periodStart, setPeriodStart] = useState(todayMinus(90))
  const [periodEnd, setPeriodEnd] = useState(new Date().toISOString().split('T')[0])
  const [params, setParams] = useState({ start: periodStart, end: periodEnd })

  const { data, isLoading } = useQuery({
    queryKey: ['reports', 'contribution-reconciliation', params.start, params.end],
    queryFn: () => reportsApi.contributionReconciliation(params.start, params.end).then((r) => r.data),
    enabled: !!params.start && !!params.end,
  })

  const fmt = (v: string | number) =>
    `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2 })}`

  const summary = data
    ? [
        { label: 'Employers', value: data.summary.employer_count },
        { label: 'Records', value: data.summary.record_count },
        { label: 'Employee Contributions', value: fmt(data.summary.total_employee_contributions) },
        { label: 'Employer Contributions', value: fmt(data.summary.total_employer_contributions) },
        { label: 'Total Contributions', value: fmt(data.summary.total_contributions) },
      ]
    : []

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end gap-4">
        <div className="space-y-1">
          <Label htmlFor="period-start">Period Start</Label>
          <Input
            id="period-start"
            type="date"
            value={periodStart}
            onChange={(e) => setPeriodStart(e.target.value)}
            className="w-44"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="period-end">Period End</Label>
          <Input
            id="period-end"
            type="date"
            value={periodEnd}
            onChange={(e) => setPeriodEnd(e.target.value)}
            className="w-44"
          />
        </div>
        <Button onClick={() => setParams({ start: periodStart, end: periodEnd })}>Run Report</Button>
      </div>

      <ReportViewer<ContributionReconciliationRow>
        title="Contribution Reconciliation"
        description="Employee and employer contributions grouped by employer."
        columns={columns}
        rows={data?.rows ?? []}
        summary={summary}
        isLoading={isLoading}
        generatedAt={data?.generated_at}
        csvFilename={`contribution-reconciliation-${params.start}-${params.end}.csv`}
        noRowsMessage="No contribution records found for this period."
      />
    </div>
  )
}

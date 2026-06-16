import { useQuery } from '@tanstack/react-query'
import { reportsApi, AnnuitantRow } from '@/lib/api'
import { ReportViewer, ColumnDef } from '@/components/reports/ReportViewer'
import { Badge } from '@/components/ui/badge'
import { CheckCircle2, Circle } from 'lucide-react'

const columns: ColumnDef<AnnuitantRow>[] = [
  { key: 'member_number', label: 'Member #' },
  {
    key: 'last_name',
    label: 'Name',
    render: (_, row) => `${row.last_name}, ${row.first_name}`,
  },
  {
    key: 'member_status',
    label: 'Member Status',
    render: (v) => <span className="capitalize">{String(v).replace('_', ' ')}</span>,
  },
  {
    key: 'case_status',
    label: 'Case Status',
    render: (v) =>
      v ? (
        <Badge variant={v === 'active' ? 'default' : 'secondary'} className="capitalize">
          {String(v)}
        </Badge>
      ) : (
        <span className="text-muted-foreground text-xs">—</span>
      ),
  },
  { key: 'retirement_date', label: 'Retirement Date' },
  {
    key: 'benefit_option_type',
    label: 'Option',
    render: (v) =>
      v ? (
        <span className="capitalize">{String(v).replace(/_/g, ' ')}</span>
      ) : (
        <span className="text-muted-foreground">—</span>
      ),
  },
  {
    key: 'final_monthly_annuity',
    label: 'Monthly Annuity',
    className: 'text-right font-medium',
    render: (v) =>
      v != null ? (
        `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2 })}`
      ) : (
        <span className="text-muted-foreground">—</span>
      ),
  },
  {
    key: 'payments_started',
    label: 'Payments Started',
    className: 'text-center',
    render: (v) =>
      v ? (
        <CheckCircle2 className="mx-auto h-4 w-4 text-green-600" />
      ) : (
        <Circle className="text-muted-foreground mx-auto h-4 w-4" />
      ),
  },
  { key: 'first_payment_date', label: 'First Payment', render: (v) => v ?? '—' },
]

export default function AnnuitantExport() {
  const { data, isLoading } = useQuery({
    queryKey: ['reports', 'annuitants'],
    queryFn: () => reportsApi.annuitants().then((r) => r.data),
  })

  const fmt = (v: string | number) =>
    `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2 })}`

  const summary = data
    ? [
        { label: 'Total Annuitants', value: data.summary.total_annuitants },
        { label: 'With Approved Case', value: data.summary.annuitants_with_approved_case },
        { label: 'Monthly Outlay', value: fmt(data.summary.total_monthly_outlay) },
      ]
    : []

  return (
    <div className="space-y-4">
      {data?.summary.note && (
        <p className="text-muted-foreground text-xs">{data.summary.note}</p>
      )}
      <ReportViewer<AnnuitantRow>
        title="Annuitant Export"
        description="All annuitant and retired members with approved retirement cases."
        columns={columns}
        rows={data?.rows ?? []}
        summary={summary}
        isLoading={isLoading}
        generatedAt={data?.generated_at}
        csvFilename="annuitants.csv"
        noRowsMessage="No annuitant or retired members found."
      />
    </div>
  )
}

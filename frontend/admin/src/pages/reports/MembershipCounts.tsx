import { useQuery } from '@tanstack/react-query'
import { reportsApi, MembershipCountRow } from '@/lib/api'
import { ReportViewer, ColumnDef } from '@/components/reports/ReportViewer'

const columns: ColumnDef<MembershipCountRow>[] = [
  {
    key: 'status',
    label: 'Status',
    render: (v) => <span className="capitalize">{String(v).replace('_', ' ')}</span>,
  },
  { key: 'count', label: 'Count', className: 'text-right font-medium' },
]

export default function MembershipCounts() {
  const { data, isLoading } = useQuery({
    queryKey: ['reports', 'membership-counts'],
    queryFn: () => reportsApi.membershipCounts().then((r) => r.data),
  })

  const summary = data
    ? [{ label: 'Total Members', value: data.summary.total_members }]
    : []

  return (
    <ReportViewer<MembershipCountRow>
      title="Membership Counts"
      description={data?.summary.note ?? 'Current member count grouped by status.'}
      columns={columns}
      rows={data?.rows ?? []}
      summary={summary}
      isLoading={isLoading}
      generatedAt={data?.generated_at}
      csvFilename="membership-counts.csv"
      noRowsMessage="No members found."
    />
  )
}

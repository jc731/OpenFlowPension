import { useQuery } from '@tanstack/react-query'
import { Users, Building2, FileText, KeyRound, TrendingUp, Clock } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { membersApi, employersApi, retirementApi, apiKeysApi } from '@/lib/api'
import { formatCurrency, formatDate } from '@/lib/utils'

function StatCard({ title, value, icon: Icon, sub }: { title: string; value: string | number; icon: React.ElementType; sub?: string }) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
      </CardContent>
    </Card>
  )
}

const statusVariant: Record<string, 'default' | 'secondary' | 'success' | 'warning' | 'destructive'> = {
  draft: 'secondary',
  approved: 'warning',
  active: 'success',
  cancelled: 'destructive',
}

export default function Dashboard() {
  const members = useQuery({ queryKey: ['members'], queryFn: () => membersApi.list({ limit: 5 }) })
  const employers = useQuery({ queryKey: ['employers'], queryFn: () => employersApi.list() })
  const cases = useQuery({ queryKey: ['retirement-cases'], queryFn: () => retirementApi.list() })
  const keys = useQuery({ queryKey: ['api-keys'], queryFn: () => apiKeysApi.list() })

  const pendingCases = cases.data?.data.filter(c => c.status === 'draft' || c.status === 'approved').length ?? '—'

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-sm text-muted-foreground">Fund administration overview</p>
      </div>

      <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Total Members"
          value={members.data?.data.length ?? '—'}
          icon={Users}
          sub="All statuses"
        />
        <StatCard
          title="Active Employers"
          value={employers.data?.data.filter(e => e.active).length ?? '—'}
          icon={Building2}
          sub="Reporting employers"
        />
        <StatCard
          title="Pending Cases"
          value={pendingCases}
          icon={FileText}
          sub="Draft + awaiting approval"
        />
        <StatCard
          title="Active API Keys"
          value={keys.data?.data.length ?? '—'}
          icon={KeyRound}
          sub="Machine access"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Recent members */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Recent Members</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {members.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
            {members.data?.data.slice(0, 5).map(m => (
              <div key={m.id} className="flex items-center justify-between py-2 border-b last:border-0">
                <div>
                  <p className="text-sm font-medium">{m.first_name} {m.last_name}</p>
                  <p className="text-xs text-muted-foreground">{m.member_number}</p>
                </div>
                <Badge variant={m.member_status === 'active' ? 'success' : 'secondary'}>
                  {m.member_status}
                </Badge>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Retirement cases queue */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Retirement Cases</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {cases.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
            {cases.data?.data.length === 0 && (
              <p className="text-sm text-muted-foreground">No cases on file.</p>
            )}
            {cases.data?.data.slice(0, 5).map(c => (
              <div key={c.id} className="flex items-center justify-between py-2 border-b last:border-0">
                <div>
                  <p className="text-sm font-medium font-mono text-xs">{c.id.slice(0, 8)}…</p>
                  <p className="text-xs text-muted-foreground">Retirement: {formatDate(c.retirement_date)}</p>
                </div>
                <div className="text-right">
                  <Badge variant={statusVariant[c.status] ?? 'secondary'}>{c.status}</Badge>
                  {c.final_monthly_annuity && (
                    <p className="text-xs text-muted-foreground mt-1">{formatCurrency(c.final_monthly_annuity)}/mo</p>
                  )}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, CalendarDays, User } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { membersApi } from '@/lib/api'
import { formatDate, formatCurrency } from '@/lib/utils'

const statusVariant: Record<string, 'default' | 'secondary' | 'success' | 'warning' | 'destructive'> = {
  active: 'success', terminated: 'secondary', annuitant: 'default',
  on_leave: 'warning', deceased: 'destructive', inactive: 'secondary',
}

const caseStatusVariant: Record<string, 'default' | 'secondary' | 'success' | 'warning' | 'destructive'> = {
  draft: 'secondary', approved: 'warning', active: 'success', cancelled: 'destructive',
}

export default function MemberDetail() {
  const { id } = useParams<{ id: string }>()

  const { data: member, isLoading } = useQuery({
    queryKey: ['member', id],
    queryFn: () => membersApi.get(id!),
    enabled: !!id,
  })

  const { data: cases } = useQuery({
    queryKey: ['member-cases', id],
    queryFn: () => membersApi.retirementCases(id!),
    enabled: !!id,
  })

  if (isLoading) return <div className="p-6 text-muted-foreground">Loading…</div>
  if (!member) return <div className="p-6 text-muted-foreground">Member not found.</div>

  const m = member.data

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" asChild>
          <Link to="/members"><ArrowLeft className="h-4 w-4" /></Link>
        </Button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold">{m.first_name} {m.last_name}</h1>
            <Badge variant={statusVariant[m.member_status] ?? 'secondary'}>{m.member_status}</Badge>
          </div>
          <p className="text-sm text-muted-foreground font-mono">{m.member_number}</p>
        </div>
      </div>

      {/* Quick facts */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground flex items-center gap-1"><User className="h-3 w-3" /> Date of Birth</p>
            <p className="font-medium mt-1">{formatDate(m.date_of_birth)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground flex items-center gap-1"><CalendarDays className="h-3 w-3" /> Cert Date</p>
            <p className="font-medium mt-1">{formatDate(m.certification_date)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground">Plan Choice</p>
            <p className="font-medium mt-1">{m.plan_choice_locked ? 'Locked' : 'Open window'}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground">Member Since</p>
            <p className="font-medium mt-1">{formatDate(m.created_at)}</p>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="employment">Employment</TabsTrigger>
          <TabsTrigger value="retirement">Retirement Cases</TabsTrigger>
          <TabsTrigger value="estimate">Benefit Estimate</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4 mt-4">
          <Card>
            <CardHeader><CardTitle className="text-base">Member Record</CardTitle></CardHeader>
            <CardContent className="grid grid-cols-2 gap-4 text-sm">
              <div><p className="text-muted-foreground">Full Name</p><p className="font-medium">{m.first_name} {m.last_name}</p></div>
              <div><p className="text-muted-foreground">Member Number</p><p className="font-mono">{m.member_number}</p></div>
              <div><p className="text-muted-foreground">Status</p><Badge variant={statusVariant[m.member_status] ?? 'secondary'}>{m.member_status}</Badge></div>
              <div><p className="text-muted-foreground">Plan Locked</p><p>{m.plan_choice_locked ? 'Yes' : 'No'}</p></div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="employment" className="mt-4">
          <Card>
            <CardHeader><CardTitle className="text-base">Employment Records</CardTitle></CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">Employment history loaded from /api/v1/members/{'{id}'}/employment — wire up when needed.</p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="retirement" className="mt-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base">Retirement Cases</CardTitle>
              <Button size="sm">New Case</Button>
            </CardHeader>
            <CardContent>
              {!cases?.data.length && <p className="text-sm text-muted-foreground">No retirement cases on file.</p>}
              {!!cases?.data.length && (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Status</TableHead>
                      <TableHead>Retirement Date</TableHead>
                      <TableHead>Option</TableHead>
                      <TableHead>Monthly Annuity</TableHead>
                      <TableHead className="w-16" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {cases.data.map(c => (
                      <TableRow key={c.id}>
                        <TableCell><Badge variant={caseStatusVariant[c.status]}>{c.status}</Badge></TableCell>
                        <TableCell>{formatDate(c.retirement_date)}</TableCell>
                        <TableCell className="capitalize">{c.benefit_option_type.replace('_', ' ')}</TableCell>
                        <TableCell>{c.final_monthly_annuity ? formatCurrency(c.final_monthly_annuity) : '—'}</TableCell>
                        <TableCell>
                          <Button variant="ghost" size="sm" asChild>
                            <Link to={`/retirement/${c.id}`}>View</Link>
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="estimate" className="mt-4">
          <BenefitEstimateTab memberId={m.id} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

function BenefitEstimateTab({ memberId }: { memberId: string }) {
  const today = new Date().toISOString().split('T')[0]
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['benefit-estimate', memberId, today],
    queryFn: () => membersApi.estimate(memberId, today),
    enabled: false,
  })

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">Benefit Estimate</CardTitle>
        <Button size="sm" onClick={() => refetch()} disabled={isLoading}>
          {isLoading ? 'Calculating…' : 'Run Estimate (today)'}
        </Button>
      </CardHeader>
      <CardContent>
        {!data && !isLoading && (
          <p className="text-sm text-muted-foreground">Click Run Estimate to calculate a benefit as of today's date.</p>
        )}
        {data && (
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 text-sm">
            <div><p className="text-muted-foreground">Tier</p><p className="font-medium">{data.data.tier}</p></div>
            <div><p className="text-muted-foreground">Plan Type</p><p className="font-medium capitalize">{data.data.plan_type}</p></div>
            <div><p className="text-muted-foreground">Formula</p><p className="font-medium capitalize">{data.data.formula_selected.replace('_', ' ')}</p></div>
            <div><p className="text-muted-foreground">FAE (Annual)</p><p className="font-medium">{formatCurrency(data.data.fae.annual)}</p></div>
            <div><p className="text-muted-foreground">Service Credit</p><p className="font-medium">{data.data.service_credit.total} yrs</p></div>
            <div className="lg:col-span-1">
              <p className="text-muted-foreground">Monthly Annuity</p>
              <p className="text-xl font-bold text-primary">{formatCurrency(data.data.final_monthly_annuity)}</p>
            </div>
            <div><p className="text-muted-foreground">COLA Type</p><p className="font-medium">{data.data.aai.rate_type}</p></div>
            <div><p className="text-muted-foreground">First Increase</p><p className="font-medium">{formatDate(data.data.aai.first_increase_date)}</p></div>
            <div>
              <p className="text-muted-foreground">Benefit Cap</p>
              <p className="font-medium">{data.data.maximum_benefit_cap.percentage}%{data.data.maximum_benefit_cap.capped ? ' (capped)' : ''}</p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

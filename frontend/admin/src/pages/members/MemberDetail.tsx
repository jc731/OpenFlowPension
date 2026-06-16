import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, CalendarDays, User, FileText } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { membersApi, documentsApi, planConfigApi } from '@/lib/api'
import { formatDate, formatCurrency, formatStatus } from '@/lib/utils'

const statusVariant: Record<string, 'default' | 'secondary' | 'success' | 'warning' | 'destructive'> = {
  active: 'success', terminated: 'secondary', annuitant: 'default',
  on_leave: 'warning', deceased: 'destructive', inactive: 'secondary',
}

const caseStatusVariant: Record<string, 'default' | 'secondary' | 'success' | 'warning' | 'destructive'> = {
  draft: 'secondary', approved: 'warning', active: 'success', cancelled: 'destructive',
}

const paymentStatusVariant: Record<string, 'default' | 'secondary' | 'success' | 'warning' | 'destructive'> = {
  pending: 'secondary', issued: 'success', held: 'warning', reversed: 'destructive', cancelled: 'destructive',
}

const claimStatusVariant: Record<string, 'default' | 'secondary' | 'success' | 'warning' | 'destructive'> = {
  draft: 'secondary', submitted: 'warning', approved: 'success', completed: 'success', cancelled: 'destructive',
}

export default function MemberDetail() {
  const { id } = useParams<{ id: string }>()

  const { data: member, isLoading } = useQuery({
    queryKey: ['member', id],
    queryFn: () => membersApi.get(id!),
    enabled: !!id,
  })

  const { data: planConfig } = useQuery({
    queryKey: ['plan-config'],
    queryFn: () => planConfigApi.get(),
    staleTime: Infinity,
  })

  const tierById = Object.fromEntries((planConfig?.data.tiers ?? []).map(t => [t.id, t.tier_label]))
  const typeById = Object.fromEntries((planConfig?.data.types ?? []).map(t => [t.id, t.plan_label]))

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
            <Badge variant={statusVariant[m.member_status] ?? 'secondary'}>
              {formatStatus(m.member_status)}
            </Badge>
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
            <p className="text-xs text-muted-foreground">Plan</p>
            <p className="font-medium mt-1">
              {m.plan_tier_id ? tierById[m.plan_tier_id] : '—'} · {m.plan_type_id ? typeById[m.plan_type_id] : '—'}
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">{m.plan_choice_locked ? 'Locked' : 'Open window'}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground">Record Created</p>
            <p className="font-medium mt-1">{formatDate(m.created_at)}</p>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="overview">
        <TabsList className="flex-wrap h-auto gap-1">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="addresses">Addresses</TabsTrigger>
          <TabsTrigger value="contacts">Contacts</TabsTrigger>
          <TabsTrigger value="employment">Employment</TabsTrigger>
          <TabsTrigger value="beneficiaries">Beneficiaries</TabsTrigger>
          <TabsTrigger value="payments">Payments</TabsTrigger>
          <TabsTrigger value="service-purchase">Service Purchase</TabsTrigger>
          <TabsTrigger value="documents">Documents</TabsTrigger>
          <TabsTrigger value="retirement">Retirement Cases</TabsTrigger>
          <TabsTrigger value="estimate">Benefit Estimate</TabsTrigger>
        </TabsList>

        {/* ── Overview ── */}
        <TabsContent value="overview" className="space-y-4 mt-4">
          <Card>
            <CardHeader><CardTitle className="text-base">Member Record</CardTitle></CardHeader>
            <CardContent className="grid grid-cols-2 gap-4 text-sm">
              <div><p className="text-muted-foreground">Full Name</p><p className="font-medium">{m.first_name} {m.last_name}</p></div>
              <div><p className="text-muted-foreground">Member Number</p><p className="font-mono">{m.member_number}</p></div>
              <div><p className="text-muted-foreground">Status</p><Badge variant={statusVariant[m.member_status] ?? 'secondary'}>{formatStatus(m.member_status)}</Badge></div>
              <div>
                <p className="text-muted-foreground">Plan</p>
                <p className="font-medium">{m.plan_tier_id ? tierById[m.plan_tier_id] : '—'} · {m.plan_type_id ? typeById[m.plan_type_id] : '—'}</p>
                <p className="text-xs text-muted-foreground">{m.plan_choice_locked ? 'Locked' : 'Open window'}</p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Addresses ── */}
        <TabsContent value="addresses" className="mt-4">
          <AddressesTab memberId={m.id} />
        </TabsContent>

        {/* ── Contacts ── */}
        <TabsContent value="contacts" className="mt-4">
          <ContactsTab memberId={m.id} />
        </TabsContent>

        {/* ── Employment ── */}
        <TabsContent value="employment" className="mt-4">
          <EmploymentTab memberId={m.id} />
        </TabsContent>

        {/* ── Beneficiaries ── */}
        <TabsContent value="beneficiaries" className="mt-4">
          <BeneficiariesTab memberId={m.id} />
        </TabsContent>

        {/* ── Payments ── */}
        <TabsContent value="payments" className="mt-4">
          <PaymentsTab memberId={m.id} />
        </TabsContent>

        {/* ── Service Purchase ── */}
        <TabsContent value="service-purchase" className="mt-4">
          <ServicePurchaseTab memberId={m.id} />
        </TabsContent>

        {/* ── Documents ── */}
        <TabsContent value="documents" className="mt-4">
          <DocumentsTab memberId={m.id} />
        </TabsContent>

        {/* ── Retirement Cases ── */}
        <TabsContent value="retirement" className="mt-4">
          <RetirementTab memberId={m.id} />
        </TabsContent>

        {/* ── Benefit Estimate ── */}
        <TabsContent value="estimate" className="mt-4">
          <BenefitEstimateTab memberId={m.id} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

// ── Addresses tab ─────────────────────────────────────────────────────────────

function AddressesTab({ memberId }: { memberId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['member-addresses', memberId],
    queryFn: () => membersApi.addresses(memberId),
  })
  const addresses = data?.data ?? []

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Addresses</CardTitle></CardHeader>
      <CardContent>
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {!isLoading && addresses.length === 0 && (
          <p className="text-sm text-muted-foreground">No addresses on file.</p>
        )}
        {addresses.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Type</TableHead>
                <TableHead>Address</TableHead>
                <TableHead>Effective</TableHead>
                <TableHead>End Date</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {addresses.map(a => (
                <TableRow key={a.id} className={a.end_date ? 'opacity-60' : ''}>
                  <TableCell className="capitalize font-medium">{a.address_type}</TableCell>
                  <TableCell>
                    <p>{a.line1}{a.line2 ? `, ${a.line2}` : ''}</p>
                    <p className="text-muted-foreground text-xs">{a.city}, {a.state} {a.zip}</p>
                  </TableCell>
                  <TableCell className="text-sm">{formatDate(a.effective_date)}</TableCell>
                  <TableCell className="text-sm">{a.end_date ? formatDate(a.end_date) : <span className="text-success text-xs">Active</span>}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

// ── Contacts tab ──────────────────────────────────────────────────────────────

function ContactsTab({ memberId }: { memberId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['member-contacts', memberId],
    queryFn: () => membersApi.contacts(memberId),
  })
  const contacts = data?.data ?? []

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Contact Information</CardTitle></CardHeader>
      <CardContent>
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {!isLoading && contacts.length === 0 && (
          <p className="text-sm text-muted-foreground">No contacts on file.</p>
        )}
        {contacts.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Type</TableHead>
                <TableHead>Value</TableHead>
                <TableHead>Primary</TableHead>
                <TableHead>Effective</TableHead>
                <TableHead>End Date</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {contacts.map(c => (
                <TableRow key={c.id} className={c.end_date ? 'opacity-60' : ''}>
                  <TableCell className="capitalize font-medium">{c.contact_type}</TableCell>
                  <TableCell>{c.value}</TableCell>
                  <TableCell>{c.is_primary ? <Badge variant="default">Primary</Badge> : null}</TableCell>
                  <TableCell className="text-sm">{formatDate(c.effective_date)}</TableCell>
                  <TableCell className="text-sm">{c.end_date ? formatDate(c.end_date) : <span className="text-xs text-success">Active</span>}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

// ── Employment tab ────────────────────────────────────────────────────────────

function EmploymentTab({ memberId }: { memberId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['member-employment', memberId],
    queryFn: () => membersApi.employment(memberId),
  })
  const records = data?.data ?? []

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Employment Records</CardTitle></CardHeader>
      <CardContent>
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {!isLoading && records.length === 0 && (
          <p className="text-sm text-muted-foreground">No employment records found.</p>
        )}
        {records.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Type</TableHead>
                <TableHead>Title / Dept</TableHead>
                <TableHead>Hire Date</TableHead>
                <TableHead>Termination</TableHead>
                <TableHead>% Time</TableHead>
                <TableHead>Primary</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {records.map(r => (
                <TableRow key={r.id} className={r.termination_date ? 'opacity-60' : ''}>
                  <TableCell className="capitalize">{r.employment_type.replace('_', ' ')}</TableCell>
                  <TableCell>
                    {r.position_title && <p className="font-medium">{r.position_title}</p>}
                    {r.department && <p className="text-xs text-muted-foreground">{r.department}</p>}
                    {!r.position_title && !r.department && <span className="text-muted-foreground">—</span>}
                  </TableCell>
                  <TableCell className="text-sm">{formatDate(r.hire_date)}</TableCell>
                  <TableCell className="text-sm">{r.termination_date ? formatDate(r.termination_date) : <span className="text-xs text-success">Active</span>}</TableCell>
                  <TableCell>{(r.percent_time * 100).toFixed(0)}%</TableCell>
                  <TableCell>{r.is_primary ? <Badge variant="default">Primary</Badge> : null}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

// ── Beneficiaries tab ─────────────────────────────────────────────────────────

function BeneficiariesTab({ memberId }: { memberId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['member-beneficiaries', memberId],
    queryFn: () => membersApi.beneficiaries(memberId),
  })
  const beneficiaries = data?.data ?? []

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Beneficiary Designations</CardTitle></CardHeader>
      <CardContent>
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {!isLoading && beneficiaries.length === 0 && (
          <p className="text-sm text-muted-foreground">No beneficiaries on file.</p>
        )}
        {beneficiaries.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name / Org</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Relationship</TableHead>
                <TableHead>Share</TableHead>
                <TableHead>Primary</TableHead>
                <TableHead>Effective</TableHead>
                <TableHead>End Date</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {beneficiaries.map(b => (
                <TableRow key={b.id} className={b.end_date ? 'opacity-60' : ''}>
                  <TableCell className="font-medium">
                    {b.first_name || b.last_name
                      ? `${b.first_name ?? ''} ${b.last_name ?? ''}`.trim()
                      : b.org_name ?? '—'}
                  </TableCell>
                  <TableCell className="capitalize">{b.beneficiary_type}</TableCell>
                  <TableCell className="capitalize">{b.relationship}</TableCell>
                  <TableCell>{b.share_percent != null ? `${b.share_percent}%` : '—'}</TableCell>
                  <TableCell>{b.is_primary ? <Badge variant="default">Primary</Badge> : null}</TableCell>
                  <TableCell className="text-sm">{formatDate(b.effective_date)}</TableCell>
                  <TableCell className="text-sm">{b.end_date ? formatDate(b.end_date) : <span className="text-xs text-success">Active</span>}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

// ── Payments tab ──────────────────────────────────────────────────────────────

function PaymentsTab({ memberId }: { memberId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['member-payments', memberId],
    queryFn: () => membersApi.payments(memberId),
  })
  const payments = data?.data ?? []

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Payment History</CardTitle></CardHeader>
      <CardContent>
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {!isLoading && payments.length === 0 && (
          <p className="text-sm text-muted-foreground">No payments on record.</p>
        )}
        {payments.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Period</TableHead>
                <TableHead>Payment Date</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Gross</TableHead>
                <TableHead>Net</TableHead>
                <TableHead>Method</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {payments.map(p => (
                <TableRow key={p.id}>
                  <TableCell className="text-sm text-muted-foreground">{formatDate(p.period_start)} – {formatDate(p.period_end)}</TableCell>
                  <TableCell className="text-sm">{formatDate(p.payment_date)}</TableCell>
                  <TableCell className="capitalize text-sm">{p.payment_type.replace('_', ' ')}</TableCell>
                  <TableCell>{formatCurrency(p.gross_amount)}</TableCell>
                  <TableCell className="font-medium">{formatCurrency(p.net_amount)}</TableCell>
                  <TableCell className="capitalize text-sm">{p.payment_method}</TableCell>
                  <TableCell><Badge variant={paymentStatusVariant[p.status] ?? 'secondary'}>{p.status}</Badge></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

// ── Service Purchase tab ──────────────────────────────────────────────────────

function ServicePurchaseTab({ memberId }: { memberId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['member-service-purchase', memberId],
    queryFn: () => membersApi.servicePurchaseClaims(memberId),
  })
  const claims = data?.data ?? []

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Service Purchase Claims</CardTitle></CardHeader>
      <CardContent>
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {!isLoading && claims.length === 0 && (
          <p className="text-sm text-muted-foreground">No service purchase claims on file.</p>
        )}
        {claims.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Type</TableHead>
                <TableHead>Period</TableHead>
                <TableHead>Credit</TableHead>
                <TableHead>Cost Total</TableHead>
                <TableHead>Cost Paid</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {claims.map(c => (
                <TableRow key={c.id}>
                  <TableCell className="capitalize font-medium">{c.purchase_type.replace('_', ' ')}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{formatDate(c.period_start)} – {formatDate(c.period_end)}</TableCell>
                  <TableCell className="text-sm">{c.credit_years} yrs</TableCell>
                  <TableCell>{formatCurrency(c.cost_total)}</TableCell>
                  <TableCell>{formatCurrency(c.cost_paid)}</TableCell>
                  <TableCell><Badge variant={claimStatusVariant[c.status] ?? 'secondary'}>{c.status}</Badge></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

// ── Documents tab ─────────────────────────────────────────────────────────────

function DocumentsTab({ memberId }: { memberId: string }) {
  const { data: docsData, isLoading: docsLoading, refetch } = useQuery({
    queryKey: ['member-documents', memberId],
    queryFn: () => membersApi.documents(memberId),
  })
  const { data: templatesData } = useQuery({
    queryKey: ['document-templates'],
    queryFn: () => documentsApi.templates(),
  })
  const documents = docsData?.data ?? []
  const templates = templatesData?.data ?? []

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <CardTitle className="text-base">Generated Documents</CardTitle>
        {templates.length > 0 && (
          <GenerateDocumentButton memberId={memberId} templates={templates} onSuccess={() => refetch()} />
        )}
      </CardHeader>
      <CardContent>
        {docsLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {!docsLoading && documents.length === 0 && (
          <p className="text-sm text-muted-foreground">No documents generated yet.</p>
        )}
        {documents.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Filename</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Generated</TableHead>
                <TableHead className="w-20" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {documents.map(d => (
                <TableRow key={d.id}>
                  <TableCell className="font-mono text-xs">{d.filename}</TableCell>
                  <TableCell>
                    <Badge variant={d.status === 'ready' ? 'success' : d.status === 'failed' ? 'destructive' : 'secondary'}>
                      {d.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm">{formatDate(d.created_at)}</TableCell>
                  <TableCell>
                    {d.status === 'ready' && (
                      <a
                        href={documentsApi.downloadUrl(d.id)}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                      >
                        <FileText className="h-3 w-3" /> PDF
                      </a>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

function GenerateDocumentButton({
  memberId,
  templates,
  onSuccess,
}: {
  memberId: string
  templates: Array<{ id: string; slug: string; display_name: string }>
  onSuccess: () => void
}) {
  const [generating, setGenerating] = useState(false)
  const [selectedSlug, setSelectedSlug] = useState(templates[0]?.slug ?? '')

  const handleGenerate = async () => {
    if (!selectedSlug) return
    setGenerating(true)
    try {
      await documentsApi.generate(selectedSlug, memberId)
      onSuccess()
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="flex items-center gap-2 shrink-0">
      <select
        value={selectedSlug}
        onChange={e => setSelectedSlug(e.target.value)}
        className="h-8 rounded-md border border-input bg-background px-2 text-sm"
      >
        {templates.map(t => (
          <option key={t.id} value={t.slug}>{t.display_name}</option>
        ))}
      </select>
      <Button size="sm" onClick={handleGenerate} disabled={generating || !selectedSlug}>
        {generating ? 'Generating…' : 'Generate'}
      </Button>
    </div>
  )
}

// ── Retirement tab ────────────────────────────────────────────────────────────

function RetirementTab({ memberId }: { memberId: string }) {
  const { data: cases } = useQuery({
    queryKey: ['member-cases', memberId],
    queryFn: () => membersApi.retirementCases(memberId),
  })
  const data = cases?.data ?? []

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">Retirement Cases</CardTitle>
        <Button size="sm" variant="outline">New Case</Button>
      </CardHeader>
      <CardContent>
        {data.length === 0 && <p className="text-sm text-muted-foreground">No retirement cases on file.</p>}
        {data.length > 0 && (
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
              {data.map(c => (
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
  )
}

// ── Benefit Estimate tab ──────────────────────────────────────────────────────

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

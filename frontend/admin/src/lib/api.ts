import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

export default api

export function setAuthToken(token: string | null) {
  if (token) {
    api.defaults.headers.common['Authorization'] = `Bearer ${token}`
  } else {
    delete api.defaults.headers.common['Authorization']
  }
}

// ── Member types ──────────────────────────────────────────────────────────────

export interface Member {
  id: string
  member_number: string
  first_name: string
  last_name: string
  date_of_birth: string
  member_status: string
  plan_tier_id: string | null
  plan_type_id: string | null
  certification_date: string | null
  plan_choice_locked: boolean
  created_at: string
}

export interface MemberCreate {
  first_name: string
  last_name: string
  date_of_birth: string
  member_number?: string
  certification_date?: string
}

export interface MemberAddress {
  id: string
  member_id: string
  address_type: string
  line1: string
  line2: string | null
  city: string
  state: string
  zip: string
  country: string
  effective_date: string
  end_date: string | null
}

export interface MemberContact {
  id: string
  member_id: string
  contact_type: string
  value: string
  is_primary: boolean
  effective_date: string
  end_date: string | null
}

// ── Employer types ────────────────────────────────────────────────────────────

export interface Employer {
  id: string
  name: string
  employer_code: string
  employer_type: string
  active: boolean
  created_at: string
  updated_at: string
}

// ── Employment types ──────────────────────────────────────────────────────────

export interface EmploymentRecord {
  id: string
  member_id: string
  employer_id: string
  employment_type: string
  position_title: string | null
  department: string | null
  hire_date: string
  termination_date: string | null
  termination_reason: string | null
  percent_time: number
  is_primary: boolean
  created_at: string
  updated_at: string
}

export interface SalaryHistory {
  id: string
  employment_id: string
  annual_salary: string
  effective_date: string
  end_date: string | null
}

// ── Beneficiary types ─────────────────────────────────────────────────────────

export interface Beneficiary {
  id: string
  member_id: string
  beneficiary_type: string
  relationship: string
  is_primary: boolean
  first_name: string | null
  last_name: string | null
  date_of_birth: string | null
  ssn_last_four: string | null
  org_name: string | null
  linked_member_id: string | null
  share_percent: number | null
  effective_date: string
  end_date: string | null
}

export interface BeneficiaryBankAccount {
  id: string
  beneficiary_id: string
  bank_name: string
  routing_number: string
  account_last_four: string
  account_type: string
  is_primary: boolean
  effective_date: string
  end_date: string | null
}

// ── Payment types ─────────────────────────────────────────────────────────────

export interface PaymentDeduction {
  id: string
  payment_id: string
  deduction_order_id: string | null
  deduction_type: string
  deduction_code: string | null
  amount: string
  is_pretax: boolean
  note: string | null
  created_at: string
}

export interface Payment {
  id: string
  member_id: string
  bank_account_id: string | null
  period_start: string
  period_end: string
  payment_date: string
  gross_amount: string
  net_amount: string
  payment_type: string
  status: string
  payment_method: string
  check_number: string | null
  issued_at: string | null
  note: string | null
  created_at: string
  deductions: PaymentDeduction[]
}

// ── Service purchase types ────────────────────────────────────────────────────

export interface ServicePurchasePayment {
  id: string
  claim_id: string
  amount: string
  payment_date: string
  created_at: string
}

export interface ServicePurchaseClaim {
  id: string
  member_id: string
  purchase_type: string
  status: string
  credit_entry_type: string
  credit_years: string
  period_start: string
  period_end: string
  cost_total: string
  cost_paid: string
  cost_breakdown: Record<string, unknown>
  installment_allowed: boolean
  credit_grant_on: string
  approved_at: string | null
  approved_by: string | null
  completed_at: string | null
  cancelled_at: string | null
  cancel_reason: string | null
  params: Record<string, unknown>
  notes: string | null
  created_at: string
  payments: ServicePurchasePayment[]
}

// ── Document types ────────────────────────────────────────────────────────────

export interface DocumentTemplate {
  id: string
  slug: string
  display_name: string
  description: string | null
  active: boolean
}

export interface GeneratedDocument {
  id: string
  template_id: string
  member_id: string | null
  generated_by: string | null
  params: Record<string, unknown>
  filename: string
  status: string
  created_at: string
}

// ── Third-party entity types ──────────────────────────────────────────────────

export interface ThirdPartyEntity {
  id: string
  name: string
  entity_type: string
  address_line1: string | null
  address_line2: string | null
  city: string | null
  state: string | null
  zip_code: string | null
  phone: string | null
  email: string | null
  ein: string | null
  bank_routing_number: string | null
  bank_account_last_four: string | null
}

// ── Billing types ─────────────────────────────────────────────────────────────

export interface InvoicePayment {
  id: string
  invoice_id: string
  amount: number
  payment_date: string
  payment_method: string
  note: string | null
  created_at: string
}

export interface Invoice {
  id: string
  employer_id: string
  invoice_type: string
  status: string
  period_start: string | null
  period_end: string | null
  amount_due: number
  amount_paid: number
  interest_accrued: number
  due_date: string
  line_items: unknown[]
  source_report_ids: unknown[]
  note: string | null
  created_by: string | null
  issued_at: string | null
  paid_at: string | null
  voided_at: string | null
  voided_by: string | null
  void_reason: string | null
  payments: InvoicePayment[]
  created_at: string
}

export interface ContributionRate {
  id: string
  employee_rate: number
  employer_rate: number
  effective_date: string
  end_date: string | null
  employer_id: string | null
  employment_type: string | null
  note: string | null
}

// ── System config types ───────────────────────────────────────────────────────

export interface SystemConfigEntry {
  id: string
  config_key: string
  config_value: unknown
  effective_date: string
  superseded_date: string | null
  note: string | null
  set_at: string
}

// ── Retirement case types ─────────────────────────────────────────────────────

export interface RetirementCase {
  id: string
  member_id: string
  member_number: string | null
  member_first_name: string | null
  member_last_name: string | null
  status: 'draft' | 'approved' | 'active' | 'cancelled'
  retirement_date: string
  benefit_option_type: string
  final_monthly_annuity: string | null
  created_at: string
}

// ── API key types ─────────────────────────────────────────────────────────────

export interface ApiKey {
  id: string
  name: string
  key_prefix: string
  scopes: string[]
  active: boolean
  expires_at: string | null
  last_used_at: string | null
  created_at: string
}

// ── Benefit estimate types ────────────────────────────────────────────────────

export interface BenefitEstimate {
  tier: string
  plan_type: string
  final_monthly_annuity: string
  formula_selected: string
  fae: { annual: string; method_used: string }
  service_credit: { total: string }
  aai: { rate_type: string; first_increase_date: string }
  hb2616_minimum: { minimum_monthly: string; supplemental_payment: string }
  maximum_benefit_cap: { percentage: string; capped: boolean }
}

// ── Payroll types ─────────────────────────────────────────────────────────────

export interface PayrollReportRow {
  id: string
  member_number: string
  member_id: string | null
  employment_id: string | null
  period_start: string
  period_end: string
  gross_earnings: string
  employee_contribution: string
  employer_contribution: string
  days_worked: number
  status: 'pending' | 'applied' | 'flagged' | 'error' | 'skipped'
  error_message: string | null
  validation_warnings: string[] | null
  created_at: string
}

export interface PayrollReport {
  id: string
  employer_id: string
  source_format: string
  source_filename: string | null
  status: string
  row_count: number
  processed_count: number
  error_count: number
  skipped_count: number
  submitted_by: string | null
  note: string | null
  created_at: string
  rows?: PayrollReportRow[]
}

// ── API functions ─────────────────────────────────────────────────────────────

export const membersApi = {
  list: (params?: { status?: string; q?: string; employer_id?: string; limit?: number; offset?: number }) =>
    api.get<Member[]>('/members/', { params }),
  get: (id: string) => api.get<Member>(`/members/${id}`),
  create: (data: MemberCreate) => api.post<Member>('/members/', data),
  estimate: (id: string, retirementDate: string) =>
    api.get<BenefitEstimate>(`/members/${id}/benefit-estimate`, {
      params: { retirement_date: retirementDate },
    }),
  retirementCases: (id: string) =>
    api.get<RetirementCase[]>(`/members/${id}/retirement-cases`),
  employment: (id: string) =>
    api.get<EmploymentRecord[]>(`/members/${id}/employment/`),
  addresses: (id: string) =>
    api.get<MemberAddress[]>(`/members/${id}/addresses`),
  contacts: (id: string) =>
    api.get<MemberContact[]>(`/members/${id}/contacts`),
  beneficiaries: (id: string, activeOnly = false) =>
    api.get<Beneficiary[]>(`/members/${id}/beneficiaries`, { params: { active_only: activeOnly } }),
  payments: (id: string) =>
    api.get<Payment[]>(`/members/${id}/payments`),
  servicePurchaseClaims: (id: string) =>
    api.get<ServicePurchaseClaim[]>(`/members/${id}/service-purchase/claims`),
  documents: (id: string) =>
    api.get<GeneratedDocument[]>(`/members/${id}/documents`),
}

export const employersApi = {
  list: () => api.get<Employer[]>('/employers/'),
  get: (id: string) => api.get<Employer>(`/employers/${id}`),
  invoices: (id: string) => api.get<Invoice[]>(`/employers/${id}/billing/invoices`),
}

export const retirementApi = {
  list: () => api.get<RetirementCase[]>('/retirement-cases'),
  get: (id: string) => api.get<RetirementCase>(`/retirement-cases/${id}`),
  approve: (id: string) => api.post(`/retirement-cases/${id}/approve`),
  activate: (id: string, firstPaymentDate: string) =>
    api.post(`/retirement-cases/${id}/activate`, { first_payment_date: firstPaymentDate }),
  cancel: (id: string, reason?: string) =>
    api.post(`/retirement-cases/${id}/cancel`, { cancel_reason: reason }),
}

export const payrollApi = {
  list: (params?: { employer_id?: string; limit?: number }) =>
    api.get<PayrollReport[]>('/payroll-reports', { params }),
  get: (id: string) => api.get<PayrollReport>(`/payroll-reports/${id}`),
  uploadCsv: (employerId: string, file: File, note?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (note) form.append('note', note)
    return api.post<PayrollReport>(
      `/employers/${employerId}/payroll-reports/upload`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    )
  },
}

export const apiKeysApi = {
  list: (includeRevoked = false) =>
    api.get<ApiKey[]>('/api-keys', { params: { include_revoked: includeRevoked } }),
  create: (data: { name: string; scopes: string[]; expires_at?: string }) =>
    api.post<{ key: ApiKey; plaintext_key: string }>('/api-keys', data),
  revoke: (id: string) => api.post(`/api-keys/${id}/revoke`),
  rotate: (id: string) => api.post<{ key: ApiKey; plaintext_key: string }>(`/api-keys/${id}/rotate`),
}

export const documentsApi = {
  templates: () => api.get<DocumentTemplate[]>('/document-templates'),
  generate: (slug: string, memberId: string, params?: Record<string, unknown>) =>
    api.post<GeneratedDocument>('/documents/generate', { slug, member_id: memberId, params: params ?? {} }),
  downloadUrl: (docId: string) => `/api/v1/documents/${docId}/download`,
}

export const thirdPartyEntitiesApi = {
  list: (activeOnly = true) =>
    api.get<ThirdPartyEntity[]>('/third-party-entities', { params: { active_only: activeOnly } }),
  get: (id: string) => api.get<ThirdPartyEntity>(`/third-party-entities/${id}`),
}

export const billingApi = {
  rates: (employerId?: string) =>
    api.get<ContributionRate[]>('/billing/rates', { params: employerId ? { employer_id: employerId } : undefined }),
  invoices: (employerId: string) =>
    api.get<Invoice[]>(`/employers/${employerId}/billing/invoices`),
}

// ── Plan config types ─────────────────────────────────────────────────────────

export interface PlanTierRead {
  id: string
  tier_code: string
  tier_label: string
}

export interface PlanTypeRead {
  id: string
  plan_code: string
  plan_label: string
}

export interface PlanConfigResponse {
  tiers: PlanTierRead[]
  types: PlanTypeRead[]
}

export const planConfigApi = {
  get: () => api.get<PlanConfigResponse>('/members/plan-config'),
}

export interface SystemConfigCreate {
  config_key: string
  config_value: Record<string, unknown>
  effective_date: string
  note?: string
}

export const systemConfigApi = {
  list: () => api.get<SystemConfigEntry[]>('/system-configurations'),
  create: (data: SystemConfigCreate) => api.post<SystemConfigEntry>('/system-configurations', data),
}

// ── Report types ──────────────────────────────────────────────────────────────

export interface ContributionReconciliationRow {
  employer_id: string
  employer_name: string
  employer_code: string
  total_employee_contributions: string
  total_employer_contributions: string
  total_contributions: string
  record_count: number
}

export interface ContributionReconciliationSummary {
  total_employee_contributions: string
  total_employer_contributions: string
  total_contributions: string
  employer_count: number
  record_count: number
}

export interface ContributionReconciliationReport {
  report_type: string
  generated_at: string
  parameters: Record<string, string | null>
  summary: ContributionReconciliationSummary
  rows: ContributionReconciliationRow[]
}

export interface DelinquencyRow {
  employer_id: string
  employer_name: string
  employer_code: string
  invoice_id: string
  invoice_type: string
  invoice_status: string
  due_date: string
  amount_due: string
  amount_paid: string
  outstanding: string
  days_overdue: number
}

export interface DelinquencySummary {
  total_outstanding: string
  invoice_count: number
  employer_count: number
}

export interface DelinquencyReport {
  report_type: string
  generated_at: string
  parameters: Record<string, string | null>
  summary: DelinquencySummary
  rows: DelinquencyRow[]
}

export interface MembershipCountRow {
  status: string
  count: number
}

export interface MembershipCountSummary {
  total_members: number
  note: string
}

export interface MembershipCountReport {
  report_type: string
  generated_at: string
  parameters: Record<string, never>
  summary: MembershipCountSummary
  rows: MembershipCountRow[]
}

export interface AnnuitantRow {
  member_id: string
  member_number: string
  first_name: string
  last_name: string
  member_status: string
  retirement_date: string | null
  benefit_option_type: string | null
  case_status: string | null
  final_monthly_annuity: string | null
  first_payment_date: string | null
  payments_started: boolean
}

export interface AnnuitantSummary {
  total_annuitants: number
  annuitants_with_approved_case: number
  total_monthly_outlay: string
  note: string
}

export interface AnnuitantReport {
  report_type: string
  generated_at: string
  parameters: Record<string, never>
  summary: AnnuitantSummary
  rows: AnnuitantRow[]
}

export const reportsApi = {
  contributionReconciliation: (
    periodStart: string,
    periodEnd: string,
    employerId?: string,
  ) =>
    api.get<ContributionReconciliationReport>('/reports/contribution-reconciliation', {
      params: {
        period_start: periodStart,
        period_end: periodEnd,
        ...(employerId ? { employer_id: employerId } : {}),
      },
    }),

  delinquency: (asOf?: string) =>
    api.get<DelinquencyReport>('/reports/delinquency', {
      params: asOf ? { as_of: asOf } : undefined,
    }),

  membershipCounts: () =>
    api.get<MembershipCountReport>('/reports/membership-counts'),

  annuitants: () =>
    api.get<AnnuitantReport>('/reports/annuitants'),
}

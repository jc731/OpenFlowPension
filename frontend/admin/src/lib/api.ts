import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

// In development, the backend uses a dev-admin bypass when no Authorization header
// is present. When Keycloak JWT integration ships, add a request interceptor here
// that injects the Bearer token from the auth context.

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

// ── Employer types ────────────────────────────────────────────────────────────

export interface Employer {
  id: string
  name: string
  employer_code: string
  active: boolean
  created_at: string
}

// ── Employment types ──────────────────────────────────────────────────────────

export interface EmploymentRecord {
  id: string
  member_id: string
  employer_id: string
  employment_type: string
  start_date: string
  termination_date: string | null
  percent_time: number
}

// ── Salary types ──────────────────────────────────────────────────────────────

export interface SalaryHistory {
  id: string
  employment_id: string
  annual_salary: string
  effective_date: string
  end_date: string | null
}

// ── Retirement case types ─────────────────────────────────────────────────────

export interface RetirementCase {
  id: string
  member_id: string
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

// ── API functions ─────────────────────────────────────────────────────────────

export const membersApi = {
  list: (params?: { status?: string; search?: string; limit?: number; offset?: number }) =>
    api.get<Member[]>('/members', { params }),
  get: (id: string) => api.get<Member>(`/members/${id}`),
  create: (data: MemberCreate) => api.post<Member>('/members', data),
  estimate: (id: string, retirementDate: string) =>
    api.get<BenefitEstimate>(`/members/${id}/benefit-estimate`, {
      params: { retirement_date: retirementDate },
    }),
  retirementCases: (id: string) =>
    api.get<RetirementCase[]>(`/members/${id}/retirement-cases`),
}

export const employersApi = {
  list: () => api.get<Employer[]>('/employers'),
  get: (id: string) => api.get<Employer>(`/employers/${id}`),
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
  status: 'pending' | 'applied' | 'error' | 'skipped'
  error_message: string | null
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

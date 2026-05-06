# Architecture Reference

Detailed module documentation. Read this file when working on a specific module.  
For always-needed context (commands, invariants, module index) see `CLAUDE.md`.

---

## Benefit calculation engine

`POST /api/v1/calculate/benefit` — stateless; `BenefitCalculationRequest` → `BenefitCalculationResult`. Gated by `benefit:calculate`.

Service structure (`app/services/benefit/`):
- `calculator.py` — orchestrator; 15-step decision tree
- `eligibility.py` — tier determination (`cert_date < 2011-01-01 → Tier I`)
- `fae.py` — prorates salary to academic years (Jul 1–Jun 30), 20% spike cap, High-4/High-8 window selection
- `age_reduction.py` — 0.5%/month before normal age (60 Tier I, 67 Tier II)
- `aai.py` — AAI/COLA first increase date (Tier I 3% compound; Tier II ½ CPI-U)
- `max_cap.py` — 80% standard; historical table for pre-1997 terminations
- `actuarial.py` — lazy-loaded CSV tables (reversionary, J&S); `lru_cache`
- `formulas/general.py` — flat 2.2% post-1997; graduated pre-1997
- `formulas/money_purchase.py` — C&I × multiplier / actuarial factor
- `formulas/police_fire.py` — graduated formula
- `service_credit.py` — sick leave conversion, total credit

**Implemented:** General Formula (both rate periods), age reduction, sick leave, HB2616 floor, benefit cap, AAI date, J&S + reversionary options, Money Purchase, Police/Fire.  
**Not implemented:** FAE Method B (48-month actual), part-time adjustments, reciprocal service, PEP (§13), HAE (§11), income tax exclusion (§10).

### Fund portability

All fund-specific parameters externalized via `FundConfig` (`app/schemas/fund_config.py`). SURS values are defaults; pass `None` to get SURS-identical results.

`load_fund_config(as_of, session)` reads `fund_calculation_config` from `system_configurations`; falls back to `FundConfig()` if absent.

Externalized parameters by module: `eligibility.py` (tier cutoff date) · `fae.py` (window sizes, spike cap) · `age_reduction.py` (normal ages, reduction rate) · `formulas/general.py` (multiplier, bands) · `formulas/money_purchase.py` (eligibility cutoff) · `formulas/police_fire.py` (bands, max %) · `max_cap.py` (cap %, term date) · `aai.py` (COLA type, deferral age) · `service_credit.py` (method, step table) · `calculator.py` (HB2616 toggle).

Adding a new fund: seed a `system_configurations` row with key `fund_calculation_config` containing only the override fields as JSONB.

### Actuarial tables

CSVs in `data/actuarial_tables/` (120×120: beneficiary age × member age). Source Excel in `source-docs/source/`. Current: SURS 2024 Experience Review, effective 2024-07-02. Tables: `reversionary_value`, `reversionary_reduction`, `js_50pct`, `js_75pct`, `js_100pct`. Update process: see `data/actuarial_tables/README.md`.

---

## Payroll ingestion

Two intake paths, one processing engine:
- `POST /api/v1/employers/{id}/payroll-reports` — JSON batch
- `POST /api/v1/employers/{id}/payroll-reports/upload` — CSV upload

**CSV required columns:** `member_number, period_start, period_end, gross_earnings, employee_contribution, employer_contribution, days_worked`

**Processing** (`_process_row` in `app/services/payroll_service.py`):
1. Resolve `member_number` → `Member.id`
2. Find active `EmploymentRecord` at this employer
3. Duplicate check: existing non-voided `ContributionRecord` same member + employment + period → `skipped`
4. Load `service_credit_accrual_rule` config as of `period_end`
5. Compute service credit years (`monthly_floor` or `proportional_percent_time`)
6. Write `ServiceCreditEntry` (links to config row for audit trail)
7. Write `ContributionRecord`

Processing is **partial-success**: each row independently applied or errored. `error_count` + `skipped_count` + `warning_count` on the report header.

**Row statuses:** `pending` → `applied` | `flagged` | `error` | `skipped`

### Two-level validation (`app/services/payroll_validation_service.py`)

**System validation** (structural, hard block — no config needed):
- `period_end < period_start`
- `days_worked > calendar days in period`
Row fails → `status=error`, skip all business logic.

**Fund validation** (threshold-based, config-driven from `payroll_validation_config`):
- `gross_earnings > max_gross_earnings`
- `days_worked > max_days_per_period`
- Employee/employer contribution rate outside expected range ± tolerance
`mode="warn"` (default): row gets `status=flagged`, warnings stored in `validation_warnings` JSONB, still applied.  
`mode="reject"`: row gets `status=error`, not applied.

`payroll_validation_config` structure: `{"max_gross_earnings", "max_days_per_period", "employee_contribution_rate", "employer_contribution_rate", "contribution_rate_tolerance", "mode"}`.

**Tables:**
- `payroll_reports` — header; `warning_count` tracks fund-validation-flagged rows
- `payroll_report_rows` — `validation_warnings` JSONB; status includes `flagged`
- `contribution_records` — append-only C&I ledger; void pattern for corrections

---

## Net pay / W-4P engine

Service: `app/services/net_pay_service.py`. Schemas: `app/schemas/net_pay.py`.

**Four endpoints:**
- `POST /calculate/tax-withholding` — stateless W-4P calc; returns all IRS Worksheet 1B intermediate steps. `benefit:calculate` scope.
- `POST /calculate/net-pay` — stateless full check-stub; `benefit:calculate` scope.
- `GET /payments/{id}/net-pay` — DB-backed preview; resolves active `DeductionOrder` + `TaxWithholdingElection`. Read-only.
- `POST /payments/{id}/apply-net-pay` — write path; persists `PaymentDeduction` rows + updates `net_amount`. 409 if already applied. `member:write` scope.

**Math order:**
```
gross − pretax deductions = taxable gross
taxable gross − federal tax − state tax − posttax deductions − third-party disbursements = net
```
SS/Medicare not applicable to pension annuities — intentionally omitted.

**W-4P form version:** 2020+ redesign only (Steps 1–4). Pre-2020 allowance-based form not supported; see `docs/BACKLOG.md`.

**Tax config keys:**
- `federal_income_tax_withholding` — IRS Pub 15-T percentage method. Two formats:
  - 2025: `standard_withholding_deduction` (halved for Step 2 via `higher_withholding_deduction`) + `brackets`
  - 2026+: smaller `standard_withholding_deduction` (line 1g) + `brackets` with 0% band + `step2_brackets` (dedicated tables when Step 2 checked)
  - Formula auto-detects format by checking for `step2_brackets` key.
- `illinois_income_tax` — `{"tax_year", "rate"}` flat rate.

Both effective-dated — seed new row each year when IRS publishes. Auto-selected by `get_config(key, as_of, session)`.

**Service internals:** `_federal_formula_steps()` owns the full Worksheet 1B computation; returns `TaxWithholdingLineItem` with all step fields populated. `_compute_federal_withholding()` is a thin wrapper extracting `total_withheld` for the net-pay path.

**Response schemas:**
- `TaxWithholdingResult` — `withholdings: list[TaxWithholdingLineItem]`. Federal formula path populates all Worksheet 1B steps; flat/exempt/non-federal only populate `total_withheld`.
- `NetPayResult` — full check-stub: `pretax_deductions`, `taxable_gross`, `tax_withholdings`, `posttax_deductions`, `third_party_disbursements`, `net_amount`, totals.

---

## Contract and status management

Service: `app/services/contract_service.py`.

**Contract events:**
- `new_hire` → creates `EmploymentRecord` + initial `SalaryHistory`; validates `employment_type` against config
- `terminate` → sets `termination_date`; writes `terminated` status only if no other active employment remains
- `begin_leave` / `end_leave` → creates/closes `LeavePeriod`; validates `leave_type` against config
- `change_percent_time` → updates `EmploymentRecord.percent_time`; creates `SalaryHistory` if salary provided

**Admin status transitions:**
- `begin_annuity` → writes `annuitant`
- `process_refund` → writes `inactive`
- `record_death` → writes `deceased`; blocks all further writes

**Valid statuses:** `active | on_leave | terminated | inactive | annuitant | deceased`

**Transition rules** (violations → `ValueError` → 422):
- `new_hire` from: `active` (concurrent), `terminated`, `inactive`, `None`
- `terminate` from: `active`, `on_leave`
- `begin_leave` from: `active`; `end_leave` from: `on_leave`
- `begin_annuity` from: `active`, `terminated`, `inactive`
- `process_refund` from: `terminated`
- `record_death` from: any; `deceased` blocks all further writes

`member_status_history` is append-only. `Member.member_status` is denormalized for fast reads.  
Config keys: `employment_types` and `leave_types` in `system_configurations`.

---

## Retirement case module

Service: `app/services/retirement_service.py`. Model: `app/models/retirement_case.py`.  
One non-cancelled case per member enforced by service.

**Status flow:** `draft → approved → active` (or `cancelled` from draft/approved)

**Service functions:**
- `create_case` — runs benefit estimate; stores `BenefitCalculationResult` as JSONB in `calculation_snapshot`; status=draft
- `recalculate` — refreshes snapshot; draft only
- `approve_case` — locks calc; calls `survivor_service.record_election()`; calls `contract_service.begin_annuity()`; denormalizes `final_monthly_annuity`; status=approved
- `activate_case` — creates `BenefitPayment(payment_type=annuity)`; status=active
- `cancel_case` — blocked once active

`final_monthly_annuity` immutable after approval. `calculation_snapshot` serialized via `model_dump(mode='json')`.

**Endpoints** (`app/api/v1/routers/retirement.py`): `POST /members/{id}/retirement-cases` · `GET /members/{id}/retirement-cases` · `GET /retirement-cases/{id}` · `POST /retirement-cases/{id}/recalculate|approve|activate|cancel`

---

## Death and survivor benefit module

Service: `app/services/survivor_service.py`.

**Pre-retirement death** (status != `annuitant`): lump sum = sum of non-voided `employee_contribution` rows → `BenefitPayment(payment_type=death_benefit)`.

**Post-retirement death** (status == `annuitant`): driven by `MemberBenefitElection` (latest with `effective_date <= event_date`):
- `single_life` → no survivor payment
- `js_50/75/100` → survivor gets elected % of `member_monthly_annuity`
- `reversionary` → survivor gets `reversionary_monthly_amount`

Creates `BenefitPayment(payment_type=survivor_annuity)` routed to beneficiary's primary `BeneficiaryBankAccount`.

**Service functions:** `record_election` · `get_current_election` · `calculate_survivor_benefit` (read-only) · `initiate_survivor_payments` (write path)

**Endpoints** (`app/api/v1/routers/survivor.py`): `POST/GET /members/{id}/benefit-elections` · `GET /members/{id}/survivor-benefit` · `POST /members/{id}/survivor-payments`

Not yet implemented: contingent beneficiary fallback; plan-configurable lump sum continuation.

---

## Payment disbursement

Five tables:
- `member_bank_accounts` — routing plaintext (public ABA), account Fernet-encrypted. `is_primary` = default ACH. Never update fields — add new row, close old.
- `benefit_payments` — one per member per pay period. `gross_amount`/`net_amount` immutable once `status=issued`. Corrections: `status=reversed` + new payment. `payment_type`: annuity | refund | death_benefit | survivor_annuity | lump_sum | other.
- `payment_deductions` — append-only; `deduction_type` plain string (no enum migration needed). `is_pretax` drives taxable gross.
- `deduction_orders` — standing authorizations. `amount_type: fixed | percent_of_gross`. End by setting `end_date` — never delete.
- `tax_withholding_elections` — immutable; new row supersedes old. `jurisdiction` extensible string.

`net_amount = gross_amount − Σ(payment_deductions.amount)` — stored for audit/perf, not recomputed on read.

---

## Beneficiary management

Table: `beneficiaries`. `beneficiary_type`: `individual` (first/last name + optional SSN) | `estate` | `trust` | `organization` (org_name).

`linked_member_id` — if beneficiary is also a fund member, link here. Interim bridge field for the planned party model refactor (trigger: when employer contacts are added). `Beneficiary.linked_member_id` → `Beneficiary.party_id` at refactor time.

`beneficiary_bank_accounts` — ACH for survivor/death payments. Fernet-encrypted account number; `account_last_four` for display. Same immutability pattern as member bank accounts.

Endpoints: `GET/POST /api/v1/beneficiaries/{id}/bank-accounts` · `PATCH .../set-primary` · `PATCH .../close`

---

## Third-party entity management

Table: `third_party_entities`. `entity_type`: disbursement_unit | union | insurance_carrier | court | other. EIN, contact fields, Fernet-encrypted bank account, `payment_method`, `active` flag.

`DeductionOrder.third_party_entity_id` links a standing deduction to its payee. `NetPayLineItem` carries `third_party_entity_name` for check stub display.

CRUD at `/api/v1/third-party-entities`. Deactivation via `POST /{id}/deactivate` — never delete.

---

## API keys

Format: `ofp_` + 64 random hex chars. Only SHA-256 hash stored. First 12 chars (`key_prefix`) stored for display. Plaintext returned once at creation/rotation.

`get_current_user` in `deps.py` handles validation: hash → lookup `api_keys` row → check `active` + `expires_at` → update `last_used_at`.

Endpoints: `POST /api/v1/api-keys` · `GET /api/v1/api-keys` · `GET /api/v1/api-keys/{id}` · `POST /api/v1/api-keys/{id}/revoke` · `POST /api/v1/api-keys/{id}/rotate`

---

## Admin / LOB frontend

React SPA at `frontend/admin/`. Vite 6, TypeScript, Tailwind v4, shadcn/ui, React Router v7, TanStack Query, sonner, lucide-react.

```bash
cd frontend/admin
pnpm dev      # → localhost:5173 (proxies /api/* → :8000)
pnpm build
pnpm typecheck
```

Architecture: `src/lib/api.ts` (typed Axios client — all API types + functions here) · `src/lib/utils.ts` (cn, formatDate, formatCurrency) · `src/components/layout/` (AppShell, Sidebar) · `src/components/ui/` (shadcn; badge has `success`/`warning` variants) · `src/pages/` (one folder per domain).

**Implemented pages:** Dashboard · Members (list + detail with employment/salary/cases/estimate) · Employers · Retirement Cases (approve/activate/cancel) · Payroll Reports (CSV upload, row-level status) · System Config (read-only placeholder) · API Keys (create/revoke/rotate with plaintext reveal).

Forms/letters deferred — will be one module, not piecemeal. Member portal: separate frontend, not started.

---

## Plan choice

Members select `plan_tier` + `plan_type` at enrollment. `plan_choice_locked=True` = hard close.  
Endpoints: `POST /api/v1/members/{id}/plan-choice` · `POST /api/v1/members/{id}/plan-choice/lock`  
Service: `app/services/plan_choice_service.py`.

---

## Member benefit estimate endpoint

`GET /api/v1/members/{id}/benefit-estimate?retirement_date=YYYY-MM-DD` — assembles `BenefitCalculationRequest` from DB (salary history, service credit, contributions, employment type) then delegates to `calculate_benefit()`. No new math.

Params: `retirement_date` (required) · `sick_leave_days` (default 0) · `benefit_option_type` (default `single_life`) · `beneficiary_age`.  
Raises 422 if missing cert date, plan choice, or salary history.  
Service: `app/services/benefit_estimate_service.py`.

---

## System configuration keys

All fund rules in `system_configurations` (`key`, `config_value` JSONB, `effective_date`). Looked up via `get_config(key, as_of, session)`.

### Seeded keys

| Key | Structure | Purpose |
|---|---|---|
| `service_credit_accrual_rule` | `{"rule": "monthly_floor" \| "proportional_percent_time"}` | Service credit computation rule |
| `employment_types` | `{"types": [...]}` | Valid employment type whitelist |
| `leave_types` | `{"types": [...]}` | Valid leave type whitelist |
| `fund_calculation_config` | See `app/schemas/fund_config.py` | Benefit calc params; optional (falls back to SURS defaults) |
| `federal_income_tax_withholding` | 2025: `{standard_withholding_deduction, higher_withholding_deduction, brackets}`; 2026+: `{standard_withholding_deduction, brackets (with 0% band), step2_brackets}` | IRS Pub 15-T percentage method |
| `illinois_income_tax` | `{"tax_year": int, "rate": float}` | Illinois flat income tax rate |

### Keys required at go-live

| Key | Structure | Purpose |
|---|---|---|
| `payroll_validation_config` | `{"max_gross_earnings", "max_days_per_period", "employee_contribution_rate", "employer_contribution_rate", "contribution_rate_tolerance", "mode": "warn"\|"reject"}` | Fund-level payroll validation thresholds |
| `concurrent_employment_max_annual_credit` | `{"max_years": 1.0}` | Cap on annual service credit across concurrent positions |
| `service_purchase_rates_{type}` | `{"factors": [...], "effective_date"}` | Cost factors for service purchase quotes |

### Adding a new config key

1. Seed a row in `system_configurations` with appropriate `effective_date`
2. Call `get_config(key, as_of, session)` in the relevant service
3. Add to the table above
4. For calc parameters: add to `FundConfig` in `app/schemas/fund_config.py` and wire through `calculator.py`

---

## Key domain concepts

**Tiers/plans:** `plan_tier` (Tier I/II) + `plan_type` (Traditional/Portable) → determines `plan_configurations` row governing benefit calc. `plan_choice_locked` prevents post-window changes.

**Service credit accrual rules:** Changed 2024-09-01.
- Pre-2024-09-01: `proportional_percent_time` — credit = percent time worked
- Post-2024-09-01: `monthly_floor` — 1 day worked in a calendar month = 1/12 year

**Certification date:** Used for tier placement. `calculated` or `override` (requires note + audit fields).

**FAE (Final Average Earnings):** Highest consecutive N academic years (Jul 1–Jun 30). Tier I: 4 years; Tier II: 8 within last 10. Prorated by daily rate (annual / 365 × overlap). 20% spike cap post-1997-06-30. Leap years spanning Feb 29 compute slightly above stated rate — mathematically correct.

**Concurrent employment:** Multiple active `EmploymentRecord` rows allowed. `concurrent_employment_max_annual_credit` config caps total at 1.0 year/calendar year.

---

## MVP scenario

Jane Smith — born 1965-03-15, hired 2000-01-15 at State University of Illinois, general staff, 100% time, Tier I Traditional. Retires 2025-01-15 after 25 years. Service credit entries span both accrual rule periods. Primary beneficiary: spouse Robert Smith.

`make seed` should print ~25.0 total service credit years.

---

## Admin configuration management (planned)

Two config levels:
- **System admin** (fund IT): `fund_calculation_config`, `service_credit_accrual_rule`, validation thresholds. Currently: DB seed scripts only.
- **Fund staff**: employer records, plan assignments, employment type whitelists. Already manageable via CRUD endpoints.

Planned System Config UI (`/config`): edit `system_configurations` rows for system admins. New value = new row (never UPDATE — same immutability pattern). Require future `effective_date`. Gate behind `admin` scope.

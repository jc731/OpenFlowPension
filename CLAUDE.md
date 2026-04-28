# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

OpenFlow Pension is an open-source pension administration platform for public funds (Apache 2.0 + Commons Clause). Free to deploy and modify; cannot be sold as software itself; selling services and addons is explicitly permitted.

**Status:** Early development. Core data model, benefit calculation engine, payment disbursement, payroll ingestion, contract/status management, beneficiary management, plan choice, and DB-backed benefit estimate are built. Auth, frontend, and document generation are not yet started. Not production-ready.

---

## Commands

```bash
make up        # docker compose up (postgres, redis, api)
make migrate   # run alembic migrations against the running DB
make seed      # run scripts/seed_mvp.py (Jane Smith 25-year scenario)
make test      # pytest
make shell     # open shell inside api container
```

Run a single test file:
```bash
pytest tests/test_config_service.py -v
```

Generate an Alembic migration after model changes:
```bash
alembic revision --autogenerate -m "describe the change"
```

Generate a Fernet encryption key (needed for `.env`):
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## Stack

| Layer | Technology |
|---|---|
| API / backend | Python 3.12+ + FastAPI |
| ORM | SQLAlchemy 2.x — **async only** (`AsyncSession`, `async_sessionmaker`) |
| Migrations | Alembic |
| Database | PostgreSQL 16 |
| Background jobs | Celery + Redis (scaffolded; no tasks yet) |
| Testing | pytest + pytest-asyncio |
| Encryption | `cryptography` (Fernet) — app-level SSN encryption |
| Schemas | Pydantic v2 |
| Auth | Keycloak (user auth, not yet integrated) + API keys (machine auth, not yet implemented) |
| Portal frontend | Astro + React (not yet started) |
| Document generation | WeasyPrint (not yet started) |
| Actuarial / numerical | Pure Python + `csv` stdlib (numpy/pandas deferred) |

---

## Architecture

### Layering

```
API routers (app/api/v1/routers/)   ← thin CRUD, no business logic
        ↓
Services (app/services/)            ← all business logic lives here
        ↓
SQLAlchemy models (app/models/)     ← async ORM, PostgreSQL
```

Routers are scaffolded with basic CRUD. Business logic must live in `app/services/`, never in routers.

### Auth and principal model

All routers depend on `get_current_user()` from `app/api/deps.py`. It returns a `Principal` TypedDict:

```python
{"id": str, "principal_type": "user" | "api_key", "scopes": list[str]}
```

`"*"` in scopes means all permissions (dev/admin stub only). Planned scopes when real auth ships:

| Scope | What it gates |
|---|---|
| `member:read` | View member records |
| `member:write` | Create/update members |
| `employment:write` | Post employment and salary changes |
| `service_credit:write` | Post service credit (payroll integrations) |
| `payroll:write` | Submit payroll reports (JSON batch or CSV upload) |
| `benefit:calculate` | Call the stateless calculation endpoint |
| `admin` | Everything |

**Two auth paths are planned, handled by the same `get_current_user` dependency:**
- **Keycloak JWT** — for human users (fund staff, admin UI). Not yet integrated.
- **API keys** — for machine-to-machine (external systems, payroll integrations, employer portals). Not yet implemented. See `api_keys` in the backlog below.

Routers must never check auth logic inline. When real auth ships, only `deps.py` changes — router signatures stay the same.

### Actuarial tables

Actuarial factor tables live in `data/actuarial_tables/` as CSVs (120×120, beneficiary age × member age). Source Excel files are in `Docs/source/`. Tables are loaded at runtime by the benefit calculation engine — do not inline these values in code. Replace with fund-specific tables at deployment.

Current tables (SURS 2024 Experience Review, effective 2024-07-02):
- `reversionary_value` — value of $1/month of Option 1 reversionary annuity
- `reversionary_reduction` — member pension reduction per $1/month of reversionary annuity
- `js_50pct`, `js_75pct`, `js_100pct` — Portable plan J&S survivor factors

When the fund's actuary publishes a new experience review, add new CSVs with the updated effective date. See `data/actuarial_tables/README.md` for the update process.

### API keys (backlog — not yet implemented)

API keys provide scoped machine access without Keycloak. When implemented:

- `api_keys` table: `id`, `key_hash` (SHA-256, never store plaintext), `name`, `scopes: JSONB`, `created_at`, `expires_at`, `last_used_at`, `active: bool`
- Key generation: endpoint returns the plaintext key once on creation, then only stores the hash
- `get_current_user` checks the `Authorization: Bearer <key>` header, hashes it, looks up the `api_keys` row, validates active + not expired, returns the `Principal` with that row's scopes
- Implement before any external system is given access

### Benefit calculation engine

`POST /api/v1/calculate/benefit` — stateless endpoint; accepts all required inputs as `BenefitCalculationRequest` and returns `BenefitCalculationResult`. No member record lookup. Gated by `benefit:calculate` scope when auth ships.

Service structure: `app/services/benefit/`
- `calculator.py` — orchestrator; implements the 15-step decision tree from spec Section 15
- `eligibility.py` — tier determination (`cert_date < 2011-01-01 → Tier I`) and eligibility checks
- `service_credit.py` — sick leave conversion table, total service credit
- `fae.py` — FAE computation; prorates salary periods to academic years (Jul 1–Jun 30), applies 20% spike cap, selects best High-4 (Tier I) or High-8 (Tier II) consecutive window
- `age_reduction.py` — 0.5%/month reduction for retiring before normal age (60 Tier I, 67 Tier II)
- `aai.py` — AAI/COLA first increase date (Tier I: 3% compound; Tier II: ½ CPI-U)
- `max_cap.py` — benefit cap lookup (80% standard; age/date table for pre-1997 terminations)
- `actuarial.py` — lazy-loaded CSV actuarial tables (reversionary, J&S); cached via `lru_cache`
- `formulas/general.py` — General Formula (flat 2.2% post-1997; graduated pre-1997)
- `formulas/money_purchase.py` — Money Purchase (C&I × multiplier / actuarial factor)
- `formulas/police_fire.py` — Police/Firefighter graduated formula

**What is implemented:** General Formula (both rate periods), age reduction, sick leave credit, HB2616 minimum floor, benefit cap table, AAI start date, J&S and reversionary benefit options, Money Purchase, Police/Fire.

**What is not yet implemented:** FAE Method B (48-month actual, for 12-month contract staff), part-time adjustments (Section 3.5), reciprocal service benefit apportionment, PEP calculation (Section 13), HAE earnings limitation (Section 11), income tax exclusion (Section 10).

### Payment disbursement

Five tables handle payment generation and deductions:

- `member_bank_accounts` — one row per bank account ever added. Routing number is plaintext (public ABA data); account number is Fernet-encrypted at app layer (same pattern as SSN). `is_primary` marks the default ACH destination. Never update routing/account fields — add a new row and close the old one.
- `benefit_payments` — one row per member per pay period. `gross_amount` and `net_amount` are immutable once `status=issued`. Corrections: set `status=reversed`, create a new payment. `payment_method`: ach | wire | check | eft | other. `payment_type`: annuity | refund | death_benefit | survivor_annuity | lump_sum | other — required, drives downstream reporting and GL coding. `bank_account_id` nullable (check/wire may not reference an account row).
- `payment_deductions` — append-only ledger of deductions applied to a payment. Never UPDATE or DELETE. `deduction_type` is a plain string (not a DB enum) so new types require no migration. Well-known types: federal_tax, state_tax, medicare, health_insurance, dental, vision, life_insurance, union_dues, child_support, garnishment, other. `is_pretax` drives taxable gross computation.
- `deduction_orders` — standing authorization records (court orders, benefit elections, union cards). `amount_type: fixed | percent_of_gross`. Active orders are auto-applied when generating a payment (`apply_standing_orders=True`). End an order by setting `end_date` — never delete.
- `tax_withholding_elections` — member W-4 / state form elections. Immutable: new row supersedes old (same pattern as salary history). `jurisdiction` is an extensible string (federal, illinois, etc.).

`net_amount = gross_amount − Σ(payment_deductions.amount)`. Stored on the payment for audit and read performance — not recomputed on every read.

### Payroll ingestion

Employers submit payroll data via two intake paths that share the same processing engine:

- `POST /api/v1/employers/{id}/payroll-reports` — JSON batch (body: `PayrollReportCreate` with a `rows` array)
- `POST /api/v1/employers/{id}/payroll-reports/upload` — CSV file upload (`UploadFile`); CSV is parsed by `payroll_service.parse_csv` and fed into the same engine

**CSV format** — required columns (header row must be present):
`member_number, period_start, period_end, gross_earnings, employee_contribution, employer_contribution, days_worked`

**Processing** (`app/services/payroll_service.py`):
Each row goes through `_process_row`, which:
1. Resolves `member_number` → `Member.id`
2. Finds the active `EmploymentRecord` for that member at this employer
3. Checks for duplicate: existing non-voided `ContributionRecord` with same member + employment + period → marks `skipped`
4. Looks up `service_credit_accrual_rule` config as of `period_end` (raises error if missing)
5. Computes service credit years via `compute_service_credit_years` (rule-specific: `monthly_floor` or `proportional_percent_time`)
6. Writes a `ServiceCreditEntry` (links to the config row for audit trail)
7. Writes a `ContributionRecord` (append-only C&I ledger)

Processing is **partial-success**: each row is independently applied or error'd. The report always completes; `error_count` and `skipped_count` tell the caller what happened. Async/Celery processing of large files is deferred — see backlog.

**Three payroll tables:**
- `payroll_reports` — one per upload/batch; tracks source format, row counts, status (pending → processing → completed)
- `payroll_report_rows` — one per input row; stores raw_data JSONB verbatim for audit; resolved `member_id`/`employment_id` written back after lookup
- `contribution_records` — append-only C&I ledger; `voided_at`/`voided_by`/`void_reason` for corrections; links back to `payroll_report_rows` when posted via payroll ingestion; can also be inserted manually (payroll_report_row_id nullable)

`contribution_records` uses the same immutability pattern as `service_credit_entries`: never UPDATE or DELETE. Post a correcting entry + void the original.

### Contract and status management

Two responsibilities handled by `app/services/contract_service.py`:

**Contract events** — validated write paths for the employment lifecycle:
- `new_hire` → creates `EmploymentRecord` + initial `SalaryHistory` row; validates `employment_type` against `system_configurations` key `employment_types` (hard 400 if invalid)
- `terminate` → sets `termination_date` on `EmploymentRecord`; only writes `terminated` status if no other active employment remains (concurrent employment support)
- `begin_leave` / `end_leave` → creates/closes a `LeavePeriod` row; validates `leave_type` against `system_configurations` key `leave_types`
- `change_percent_time` → updates `EmploymentRecord.percent_time`; creates a `SalaryHistory` row if new salary provided

**Explicit status transitions** (admin actions, not auto-derived):
- `begin_annuity` → writes `annuitant` (call after first benefit payment is set up)
- `process_refund` → writes `inactive` (call after refund payment is processed)
- `record_death` → writes `deceased`; all subsequent contract writes are blocked

**Status storage**: `member_status_history` is an append-only table. Every event writes a new row. `Member.member_status` (denormalized) is kept in sync for fast reads. `get_current_status` reads the latest history row.

**Valid statuses**: `active | on_leave | terminated | inactive | annuitant | deceased`

**Transition rules** (violations raise `ValueError` → 422):
- `new_hire` from: `active` (concurrent), `terminated`, `inactive`, `None`
- `terminate` from: `active`, `on_leave`
- `begin_leave` from: `active`
- `end_leave` from: `on_leave`
- `begin_annuity` from: `active`, `terminated`, `inactive`
- `process_refund` from: `terminated`
- `record_death` from: any
- `deceased` blocks all further contract writes

**Configurable lookup tables** (must be seeded in `system_configurations`):
- `employment_types` — `{"types": ["general_staff", "academic", "police_fire", "other"]}`
- `leave_types` — `{"types": ["medical", "personal", "military", "family", "other"]}`

Both use the standard `get_config(key, as_of, session)` pattern and raise a descriptive error if the config key is missing.

### Beneficiary management

Beneficiaries are designated on a member account (`beneficiaries` table). `beneficiary_type` controls which name fields apply:
- `individual` → `first_name` + `last_name` (+ optional `ssn_encrypted` / `ssn_last_four`)
- `estate` → `org_name` (e.g. "Estate of Jane Smith")
- `trust` → `org_name`
- `organization` → `org_name`

`is_primary` distinguishes primary vs contingent beneficiaries. `share_percent` records the allocation. `effective_date` / `end_date` support designation history.

`linked_member_id` — if the beneficiary is also a pension system member, link their record here. When set, current demographic data comes from the Member record rather than the beneficiary row. This is a **bridge field for the planned party model refactor** (see Party model section below).

`beneficiary_bank_accounts` stores ACH payment destinations for survivor/death benefit payments. Same immutability pattern as `member_bank_accounts`: never update routing/account fields — add a new row and close the old one. Account numbers are Fernet-encrypted (`account_number_encrypted: BYTEA`); `account_last_four` is used for display.

Beneficiary bank account endpoints live under `GET/POST /api/v1/beneficiaries/{id}/bank-accounts` and `PATCH .../set-primary` / `.../close`.

### Plan choice

Members select a plan tier and plan type at enrollment. The plan choice window has a hard close (`plan_choice_locked=True`). Endpoints:
- `POST /api/v1/members/{id}/plan-choice` — set `plan_tier_id`, `plan_type_id`, `choice_date` (rejected if locked)
- `POST /api/v1/members/{id}/plan-choice/lock` — permanently locks the selection (validates that a choice was made first)

Service: `app/services/plan_choice_service.py`.

### Party model refactor (planned — not yet triggered)

The current data model stores demographic information (name, DOB, SSN, contact) separately for each entity type: `members`, `beneficiaries`, and (in future) employer contacts, alternate payees, etc. This causes duplication when the same natural person appears in multiple roles.

**Planned refactor:** Extract a shared `parties` table (`id`, `party_type`, `first_name`, `last_name`, `dob`, `ssn_encrypted`, etc.) and replace inline demographic fields in `members`, `beneficiaries`, and other tables with a `party_id` FK. Each entity keeps its role-specific fields (employment status, share_percent, etc.) but sources demographic data from the party record.

**Why deferred:** The full set of party types is not yet known. Refactoring prematurely means migrating again as new types emerge. The `linked_member_id` bridge field on `Beneficiary` is the interim approach — it handles the most common case (beneficiary who is also a member) without requiring a full refactor.

**Trigger condition:** Begin the refactor when **employer contacts** are added (the first non-member, non-beneficiary person type). At that point, the shared-demographics use case is proven and the full party table design becomes clear.

**What to preserve:** `Beneficiary.linked_member_id` becomes `Beneficiary.party_id`. `Member` gets its own `party_id` FK. The bridge approach is designed to be a clean rename, not a rewrite.

### Death and survivor benefit module (backlog — not yet implemented)

When a member dies, the system must:
1. Set status to `deceased` via `contract_service.record_death()`
2. Identify beneficiaries (primary first; contingent if primary has predeceased)
3. Calculate the survivor benefit: survivor annuity (reversionary option or J&S election) or lump sum death benefit, per the member's elected option and plan rules
4. Create `BenefitPayment` rows with `payment_type=death_benefit` or `payment_type=survivor_annuity`, routed to `BeneficiaryBankAccount`

Service structure (proposed): `app/services/survivor_service.py`
- `calculate_survivor_benefit(member_id, event_date, session)` → stateless calculation delegating to existing actuarial tables in `benefit/actuarial.py`
- `initiate_survivor_payments(member_id, event_date, session)` → write path creating payments

Plan rules for lump sum amounts and continuation periods should live in `system_configurations` (same config service pattern). Defer until first fund goes live.

### Disability benefit module (backlog — deferred, high complexity)

Disability benefits are intentionally excluded from the initial build. Rules vary significantly by fund and state; do not implement speculatively. Placeholder notes for when a fund requests this feature:

**Two disability types (typical):**
- **Ordinary/non-occupational** — illness or injury not job-related; typically 50% of final salary
- **Duty/occupational** — job-related injury; typically 75% of final salary; often no minimum service requirement

**Key sub-topics to implement:**
- Eligibility rules: minimum service years, age cutoffs, medical certification — store in `system_configurations`
- Benefit amount: percentage of salary at time of disability onset, not retirement FAE
- Workers' compensation offset: WC payments reduce disability benefit (dollar-for-dollar or formula); WC payment amount is stored as a `DeductionOrder` with `deduction_type=workers_compensation` using the existing deduction pattern
- Annual medical recertification: flag on a `disability_claims` table; payments suspend if recertification lapses
- Recovery: member returns to active employment; service credit and contribution history are preserved from before disability onset

**Transition events (the complex part):**
- **Disability → regular retirement**: when a disabled member reaches normal retirement age, convert to regular retirement benefit. Near-automatic; triggered by age check.
- **Disability → disability retirement**: after a qualifying period (typically 3–5 years) on temporary disability, member may be permanently converted to disability retirement with a separate benefit formula. Requires both duration AND continued medical certification.
- These two paths use different formulas — do not assume the regular `calculate_benefit()` engine applies without modification.

**Workers' comp integration options (three tiers):**
1. **Manual** — staff enters WC payment amounts per period; system applies offset. Lowest effort; sufficient for small funds.
2. **Employer reporting** — extend the payroll report CSV format with a `workers_comp_payment` column; employer reports alongside regular payroll. Medium effort; keeps intake path consistent.
3. **State WC board integration** — some states publish WC claim data via API or SFTP (e.g., IL Workers' Compensation Commission). Requires a data-sharing agreement and a polling/webhook integration layer. Highest accuracy; build only if a fund requires it.

**Data model sketch (when built):**
- New table: `disability_claims` — `member_id`, `claim_date`, `disability_type` (ordinary | duty), `onset_date`, `wc_case_number`, `benefit_amount`, `status` (active | suspended | converted | closed), `last_certified_date`
- New member status: `disability` — add to the valid statuses in `contract_service`
- New payment type: `disability_benefit` — add to `payment_type` on `benefit_payments`
- WC offsets: use existing `DeductionOrder` with `deduction_type=workers_compensation`

### Service purchase module (backlog — not yet implemented)

Members can purchase service credit for prior periods (military service, refunded service, etc.). Two-step flow:
1. **Quote** (`POST /api/v1/members/{id}/service-purchase/quote`) — stateless; takes purchase type, years, and member demographics; returns cost using rate tables from `system_configurations`
2. **Apply** (`POST /api/v1/members/{id}/service-purchase/apply`) — write path; validates payment received; posts a `ServiceCreditEntry` + a corresponding `ContributionRecord`

Rate tables: store purchase cost factors in `system_configurations` keyed by `service_purchase_rates_{type}` with effective date. Defer until fund requests the feature.

### Async payroll processing (backlog — not yet implemented)

For large files (>1,000 rows), payroll ingestion should be offloaded to a Celery task. Pattern: route creates a `PayrollReport` with `status=pending`, enqueues a Celery task with `report_id`, returns 202 Accepted immediately. Celery task fetches the report, processes rows, updates counts, sets `status=completed`. Use Redis as the Celery broker (already in docker-compose). Implement when employers are submitting production volumes.

### Contribution interest crediting (backlog — not yet implemented)

`contribution_records` accumulates the raw employee + employer contributions. Interest crediting (C&I accumulation for Money Purchase calculation) is a separate periodic process that will read `contribution_records`, apply rate tables stored in `system_configurations`, and write interest entries back. The exact crediting frequency and compounding rules differ by fund. Defer until Money Purchase is in active use.

### Tax withholding calculation engine (backlog — not yet implemented)

`POST /api/v1/calculate/tax-withholding` — stateless endpoint. Takes gross amount + W-4 election + tax year → returns computed federal and state withholding amounts. Tax brackets stored in `system_configurations` with keys like `federal_tax_brackets_2025` (JSONB), versioned by effective date — same config service pattern used everywhere else. Historic bracket lookup for prior-year payment review is supported by the config pattern but low priority. Implement before automating payroll runs.

### Routing number validation (backlog — not yet implemented)

Validate ABA routing numbers against the Federal Reserve's E-Payments Routing Directory (EPRD), which is a downloadable CSV of all valid routing numbers. Also check Fedwire eligibility for wire payments. Implement as a pre-save validation hook in `bank_account_service.add_bank_account`. Low priority until payment processing is live.

### Member benefit estimate endpoint

`GET /api/v1/members/{id}/benefit-estimate?retirement_date=YYYY-MM-DD` — DB-backed convenience wrapper for staff/admin use. Assembles a `BenefitCalculationRequest` from the member's posted salary history, service credit ledger, contribution records, and employment type, then delegates to the stateless `calculate_benefit()` engine. No new math.

Query params: `retirement_date` (required), `sick_leave_days` (default 0), `benefit_option_type` (default `single_life`), `beneficiary_age` (optional for J&S / reversionary options).

Raises 422 if member is missing certification date, plan choice, or salary history. Active members use `retirement_date` as their `termination_date`; terminated members use the most recent `termination_date` from their employment records.

Service: `app/services/benefit_estimate_service.py`.

### Config service pattern

**Never hardcode pension rules in the calculation engine.** All fund-level behavioral rules (accrual rules, contribution rates, COLA caps, etc.) live in the `system_configurations` table and are looked up at runtime via:

```python
# app/services/config_service.py
async def get_config(key: str, as_of: date, session: AsyncSession) -> dict
```

This function returns the active `config_value` JSONB for a given key as of a specific date. The calculation engine calls this for every rule lookup. Raises `ConfigNotFoundError` if no matching config exists.

Plan-level rules (multiplier, FAC window, vesting, etc.) live in `plan_configurations` rows — one row per tier + plan_type + employment_type + effective_date. Adding a new plan tier requires adding rows, not code changes.

### Service credit ledger

`service_credit_entries` is an **append-only immutable ledger**. Never UPDATE or DELETE rows. Corrections are made by inserting a new row with negative credit and setting `voided_at`/`void_reason` on the original. A service-layer guard raises if any code attempts an UPDATE on this table.

Each entry links to the `system_configurations` row that generated it via `accrual_rule_config_id` — this is critical for audit trail.

### Salary history

`salary_history` is also immutable. Never update rows. Insert a new row on every salary change.

### Encryption at rest

Sensitive strings are encrypted at the application layer using Fernet symmetric encryption (`app/crypto.py`). The `ENCRYPTION_KEY` env var holds a base64-urlsafe 32-byte key. The same encrypt/decrypt helpers are reused for all sensitive fields.

Fields using this pattern:
- `members.ssn_encrypted: BYTEA` — never logged, never returned in API responses; `ssn_last_four` (plaintext) used for display
- `member_bank_accounts.account_number_encrypted: BYTEA` — never returned in API responses; `account_last_four` used for display
- `beneficiary_bank_accounts.account_number_encrypted: BYTEA` — same pattern as member bank accounts; used for survivor/death benefit ACH payments

API response schemas must never expose any `*_encrypted` field.

### Database conventions

- All primary keys: `UUID`, generated by PostgreSQL (`gen_random_uuid()`) via `server_default=text("gen_random_uuid()")`
- All timestamps: `TIMESTAMPTZ` (timezone-aware). No naive datetimes anywhere.
- No ORM-level `cascade="all, delete"` on financial or ledger tables. Data is never deleted.
- Pydantic v2 schemas use `model_config = ConfigDict(from_attributes=True)`

---

## Key domain concepts

**Tiers and plans:** Members are assigned to a `plan_tier` (e.g., Tier I, Tier II) and a `plan_type` (e.g., Traditional, Portable) at enrollment. The combination drives which `plan_configurations` row governs their benefit calculation. `plan_choice_locked` prevents changes after the window closes.

**Service credit accrual rules:** Changed September 1, 2024.
- Pre-2024-09-01: `proportional_percent_time` — credit = percent time worked
- Post-2024-09-01: `monthly_floor` — 1 day worked in a calendar month = 1/12 year credit

**Certification date:** The date used to determine member eligibility and tier placement. Can be `calculated` or `override` (requires note and audit fields).

**Concurrent employment:** Members can have multiple simultaneous employment records. The `concurrent_employment_max_annual_credit` config caps total service credit at 1.0 years per calendar year regardless of concurrent positions.

**FAE (Final Average Earnings):** The benefit formula uses the highest consecutive N academic years of salary to compute the base benefit. Tier I uses 4 years; Tier II uses 8 within the last 10. The academic year runs July 1–June 30. Salary periods are prorated to academic years by daily rate (annual_salary / 365 × overlap days). A 20% spike cap applies to any AY after 1997-06-30 where earnings grew ≥ 20% over the prior year. Leap years cause AYs spanning Feb 29 to compute slightly above the stated annual rate — this is the mathematically correct behavior when prorating by daily rate.

---

## MVP scenario (seed_mvp.py)

Jane Smith — born 1965-03-15, hired 2000-01-15 at State University of Illinois, general staff, 100% time, Tier I Traditional. Retires 2025-01-15 after 25 years. Service credit entries span both accrual rule periods and link to correct `system_configurations` rows. Primary beneficiary: spouse Robert Smith.

Running `make seed` should print a summary showing ~25.0 total service credit years.

---

## Documentation rule

**Keep this file current as the codebase evolves.** When you:
- Add a new module or service — add it to the architecture section
- Establish a new pattern (new service layer, new encryption usage, new table type) — document the pattern here
- Add new `make` targets or CLI commands — add them to the Commands section
- Complete a previously-scaffolded layer (auth, frontend, document generation) — update the Stack table and add an architecture section for it
- Change a fund rule or config key — update the Key domain concepts section

Do not document things derivable from reading the code (function signatures, field names, file structure). Document the *why* and the *cross-cutting patterns* that require reading multiple files to understand.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

OpenFlow Pension is an open-source pension administration platform for public funds (Apache 2.0 + Commons Clause). Free to deploy and modify; cannot be sold as software itself; selling services and addons is explicitly permitted.

**Status:** Early development. Data model, benefit calculation engine, and payment disbursement are the current focus. Not production-ready.

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
| `benefit:calculate` | Call the stateless calculation endpoint |
| `admin` | Everything |

**Two auth paths are planned, handled by the same `get_current_user` dependency:**
- **Keycloak JWT** — for human users (fund staff, admin UI). Not yet integrated.
- **API keys** — for machine-to-machine (external systems, payroll integrations, SURS-style callers). Not yet implemented. See `api_keys` in the backlog below.

Routers must never check auth logic inline. When real auth ships, only `deps.py` changes — router signatures stay the same.

### Actuarial tables

SURS actuarial factor tables live in `data/actuarial_tables/` as CSVs (120×120, beneficiary age × member age). Source Excel files are in `Docs/source/`. Tables are loaded at runtime by the benefit calculation engine — do not inline these values in code.

Current tables (2024 Experience Review, effective 2024-07-02):
- `reversionary_value` — value of $1/month of Option 1 reversionary annuity
- `reversionary_reduction` — member pension reduction per $1/month of reversionary annuity
- `js_50pct`, `js_75pct`, `js_100pct` — Portable plan J&S survivor factors

When SURS publishes a new experience review, add new CSVs with the updated effective date. See `data/actuarial_tables/README.md` for the update process.

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
- `benefit_payments` — one row per member per pay period. `gross_amount` and `net_amount` are immutable once `status=issued`. Corrections: set `status=reversed`, create a new payment. `payment_method`: ach | wire | check | eft | other. `bank_account_id` nullable (check/wire may not reference an account row).
- `payment_deductions` — append-only ledger of deductions applied to a payment. Never UPDATE or DELETE. `deduction_type` is a plain string (not a DB enum) so new types require no migration. Well-known types: federal_tax, state_tax, medicare, health_insurance, dental, vision, life_insurance, union_dues, child_support, garnishment, other. `is_pretax` drives taxable gross computation.
- `deduction_orders` — standing authorization records (court orders, benefit elections, union cards). `amount_type: fixed | percent_of_gross`. Active orders are auto-applied when generating a payment (`apply_standing_orders=True`). End an order by setting `end_date` — never delete.
- `tax_withholding_elections` — member W-4 / state form elections. Immutable: new row supersedes old (same pattern as salary history). `jurisdiction` is an extensible string (federal, illinois, etc.).

`net_amount = gross_amount − Σ(payment_deductions.amount)`. Stored on the payment for audit and read performance — not recomputed on every read.

### Tax withholding calculation engine (backlog — not yet implemented)

`POST /api/v1/calculate/tax-withholding` — stateless endpoint. Takes gross amount + W-4 election + tax year → returns computed federal and state withholding amounts. Tax brackets stored in `system_configurations` with keys like `federal_tax_brackets_2025` (JSONB), versioned by effective date — same config service pattern used everywhere else. Historic bracket lookup for prior-year payment review is supported by the config pattern but low priority. Implement before automating payroll runs.

### Routing number validation (backlog — not yet implemented)

Validate ABA routing numbers against the Federal Reserve's E-Payments Routing Directory (EPRD), which is a downloadable CSV of all valid routing numbers. Also check Fedwire eligibility for wire payments. Implement as a pre-save validation hook in `bank_account_service.add_bank_account`. Low priority until payment processing is live.

### Member benefit estimate endpoint (backlog — not yet implemented)

`GET /api/v1/members/{id}/benefit-estimate` — DB-backed convenience wrapper for internal/admin use. Queries the member's salary history, service credit entries, plan tier/type, and cert date; assembles a `BenefitCalculationRequest`; and delegates to the same `calculate_benefit()` engine. No new math — just DB plumbing. Useful once an admin UI exists. Implement when the frontend is ready to consume it.

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

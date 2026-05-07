# CLAUDE.md

## What this is

OpenFlow Pension — open-source pension administration platform for public funds (Apache 2.0 + Commons Clause). Not production-ready.

**Built:** benefit calc engine, payroll ingestion (with two-level validation), payment disbursement, contract/status management, beneficiary management, plan choice, benefit estimate, death/survivor module, retirement case, API key + Keycloak JWT auth, admin/LOB frontend, net pay engine, third-party entities, W-4P tax-withholding endpoint, document generation framework, service purchase module (claims + payments + credit grant).  
**Not started:** member portal frontend, form ingest (FormSubmission table stubbed), WeasyPrint HTML templates beyond `benefit_estimate_letter`.

---

## Commands

```bash
make up        # docker compose up (postgres, redis, api)
make migrate   # run alembic migrations
make seed      # run scripts/seed_mvp.py (Jane Smith 25-year scenario)
make test      # pytest
make shell     # open shell inside api container
make preview   # build frontend + nginx on port 80 (Cloudflare Tunnel target)
```

Single test file: `pytest tests/test_config_service.py -v`  
New migration: `alembic revision --autogenerate -m "describe"`  
Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

---

## Stack

| Layer | Technology |
|---|---|
| API | Python 3.12+ + FastAPI |
| ORM | SQLAlchemy 2.x — async only (`AsyncSession`, `async_sessionmaker`) |
| Migrations | Alembic |
| Database | PostgreSQL 16 |
| Background jobs | Celery + Redis (scaffolded; no tasks yet) |
| Testing | pytest + pytest-asyncio |
| Encryption | `cryptography` (Fernet) — app-level field encryption |
| Schemas | Pydantic v2 |
| Auth | Keycloak JWT + API keys (both built) |
| Admin frontend | React + Vite + TypeScript + Tailwind v4 + shadcn/ui (`frontend/admin/`) |

---

## Architecture

### Layering

```
API routers (app/api/v1/routers/)   ← thin CRUD; no business logic
Services    (app/services/)         ← all business logic here
Models      (app/models/)           ← async SQLAlchemy ORM
```

### Auth and principal

`get_current_user()` in `app/api/deps.py` returns:
```python
{"id": str, "principal_type": "user" | "api_key", "scopes": list[str]}
```
Tokens starting with `ofp_` → API key path; others → Keycloak JWT RS256.  
`"*"` in scopes = all permissions (dev stub only).  
**Dev bypass:** `environment=development` + no auth header → stub with `scopes=["*"]`. Blocked in production.

| Scope | Gates |
|---|---|
| `member:read` | View members |
| `member:write` | Create/update members |
| `employment:write` | Employment + salary changes |
| `service_credit:write` | Service credit (payroll integrations) |
| `payroll:write` | Submit payroll reports |
| `benefit:calculate` | Stateless calc endpoints |
| `admin` | Everything |

### Core invariants — must follow

- **Config service:** never hardcode fund rules. Use `get_config(key, as_of, session)` in `app/services/config_service.py`. Raises `ConfigNotFoundError` if missing.
- **Append-only ledgers:** never UPDATE or DELETE `service_credit_entries`, `salary_history`, `contribution_records`, `payment_deductions`. Corrections = new row + void original.
- **Insert-only history:** `salary_history`, `tax_withholding_elections`, `MemberBenefitElection` — new row supersedes old; never update in place.
- **Encryption:** SSN + bank account numbers via Fernet (`app/crypto.py`). Never expose `*_encrypted` fields in API responses.
- **No cascades:** no ORM `cascade="all, delete"` on financial/ledger tables. Data is never deleted.

### DB conventions

- PKs: UUID via `server_default=text("gen_random_uuid()")`
- Timestamps: TIMESTAMPTZ everywhere — no naive datetimes
- Pydantic v2 schemas: `model_config = ConfigDict(from_attributes=True)`

---

## Module index

| Module | Service file | Notes |
|---|---|---|
| Benefit calc | `app/services/benefit/` | Stateless; 15-step decision tree; `FundConfig` portability |
| Payroll ingestion | `app/services/payroll_service.py` | Two intake paths; partial-success; validation in `payroll_validation_service.py` |
| Net pay / W-4P | `app/services/net_pay_service.py` | 2020+ W-4P only; 4 endpoints; `_federal_formula_steps()` owns IRS Pub 15-T arithmetic |
| Contract/status | `app/services/contract_service.py` | Member lifecycle state machine; `member_status_history` append-only |
| Retirement case | `app/services/retirement_service.py` | draft→approved→active; `calculation_snapshot` JSONB |
| Survivor/death | `app/services/survivor_service.py` | Pre/post-retirement paths; election-driven |
| Benefit estimate | `app/services/benefit_estimate_service.py` | DB-backed; delegates to stateless calc engine |
| Fund portability | `app/services/fund_config_service.py` | `FundConfig` schema; SURS defaults, per-key overridable |
| Third-party entities | `app/services/third_party_entity_service.py` | Payee orgs; Fernet-encrypted ACH |
| API keys | `app/services/api_key_service.py` | `ofp_` prefix; SHA-256 stored; plaintext returned once |
| Beneficiary mgmt | `app/api/v1/routers/beneficiaries.py` | `linked_member_id` bridge; bank accounts for survivor ACH |
| Config service | `app/services/config_service.py` | All fund rules route through `get_config()` |
| Admin frontend | `frontend/admin/` | `pnpm dev` → :5173; proxies `/api/*` to :8000 |
| Document generation | `app/services/document_*.py` | Declarative context spec; WeasyPrint PDF; Option A escape hatch via `EXPLICIT_ASSEMBLERS` |
| Service purchase | `app/services/service_purchase_service.py` | Claims lifecycle; 4 types (military/ope/prior_service/refund); installment payments; config-driven credit routing |

**Detailed architecture per module:** `docs/ARCHITECTURE.md`  
**Backlog items:** `docs/BACKLOG.md`

---

## System config keys

All fund rules stored in `system_configurations` table, looked up via `get_config(key, as_of, session)`.

**Seeded:** `service_credit_accrual_rule` · `employment_types` · `leave_types` · `fund_calculation_config` · `federal_income_tax_withholding` (2025 + 2026 formats differ — see `docs/ARCHITECTURE.md`) · `illinois_income_tax` · `fund_info` · `service_purchase_types` · `payroll_validation_config`  
**Required at go-live:** `concurrent_employment_max_annual_credit`

Full key schemas and adding-a-key checklist: `docs/ARCHITECTURE.md#system-configuration-keys`

---

## Documentation rule

When adding a module: add a row to the module index above + a section in `docs/ARCHITECTURE.md`.  
Backlog items (deferred, not yet built): `docs/BACKLOG.md`.  
Document the *why* and cross-cutting patterns — not what's derivable from reading the code.

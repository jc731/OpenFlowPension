# OpenFlow Pension

> Open source pension administration — built for public funds, by people who know how they actually work.

![License: Apache 2.0 + Commons Clause](https://img.shields.io/badge/license-Apache%202.0%20%2B%20Commons%20Clause-blue)
![Stack: Python + FastAPI](https://img.shields.io/badge/stack-Python%20%2B%20FastAPI-green)
![Database: PostgreSQL](https://img.shields.io/badge/database-PostgreSQL-blue)

---

## What is this

OpenFlow is a full-featured pension administration platform covering member and employer management, service credit tracking, benefit calculations, payment disbursement, tax withholding, employer billing, and reporting. It is designed to be deployed by public pension funds of any size — from single-employer systems to statewide multi-tier funds.

The software is free to use, deploy, and modify. You cannot sell it. You can sell everything around it.

---

## The philosophy

Pension administration software has historically been expensive, opaque, and controlled by a small number of vendors who understand that switching costs are high. That dynamic does not serve members or fund staff.

Our bet is simple: the software matters less than the people. OpenFlow is the foundation. The value is in implementation expertise, fund-specific configuration, and ongoing support from people who understand how defined benefit systems actually work — tier structures, reciprocal agreements, actuarial assumption changes, legislative amendments, and everything else that makes pension administration genuinely hard.

We plan to have the best people. That's the whole pitch.

---

## Core modules

| Module | What it does |
|---|---|
| **Member registry** | Employment history, beneficiary records, tier assignment, lifecycle state |
| **Service credit ledger** | Credited service, purchased service, military credit, reciprocal transfers |
| **Benefit calculation engine** | FAC/FAS formulas, tier rules, option factors, disability offsets, COLA |
| **Benefit event processing** | Retirement, disability, death, survivor elections, refunds |
| **Payment disbursement** | Annuity scheduling, withholding, 3rd party deductions, net payment runs |
| **Employer billing** | Contribution reporting, rate tables, invoice generation, reconciliation |
| **Tax tracking** | Federal/state withholding elections, 1099-R generation, exclusion ratio |
| **Document generation** | Benefit estimates, award letters, tax forms, employer reports |
| **Member/employer portal** | Self-service access to statements, estimates, reporting, and elections |

---

## Stack

| Layer | Technology |
|---|---|
| API / backend | Python 3.12+ + FastAPI |
| Database | PostgreSQL 16 |
| Admin / LOB frontend | React + Vite + TypeScript + Tailwind v4 + shadcn/ui |
| Member portal frontend | Not yet started |
| Background jobs | Celery + Redis |
| Document generation | WeasyPrint (deferred) |
| Auth | Keycloak JWT (built) + API keys (built) |
| Actuarial / numerical | Pure Python (NumPy / pandas deferred) |

---

## Getting started

**Prerequisites:** Docker, Docker Compose, Node.js 20+, pnpm.

```bash
git clone https://github.com/jc731/OpenFlowPension
cd OpenFlowPension
cp .env.example .env
make up        # start postgres, redis, api containers
make migrate   # run alembic migrations
make seed      # load the Jane Smith demo scenario (see below)
```

The API is now running at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

To start the admin frontend:

```bash
cd frontend/admin
pnpm install
pnpm dev       # → http://localhost:5173
```

---

## Preview deployment (homelab / Cloudflare Tunnel)

`make preview` builds the React SPA, starts the full stack (postgres + redis + api + nginx) on port 80, and runs migrations. Point any reverse proxy or Cloudflare Tunnel public hostname at `http://localhost:80`.

```bash
# Build frontend and start full stack on port 80
make preview

# Stop
docker compose --profile deploy down
```

**Cloudflare Tunnel setup:**

1. In Zero Trust → Networks → Tunnels, create or select your tunnel.
2. Add a public hostname (e.g. `openflow-dev.yourdomain.com`) with:
   - Service type: `HTTP`
   - URL: `localhost:80` (or `<homelab-ip>:80` if cloudflared runs elsewhere)
3. Run `make preview` — nginx serves the SPA and proxies `/api/*` to FastAPI internally.

The Swagger docs are proxied at `https://openflow-dev.yourdomain.com/docs`.

**Auth in preview:** With `KEYCLOAK_URL` unset (default), the backend dev-admin bypass stays active. To test with real Keycloak auth, also start the auth profile and set `VITE_KEYCLOAK_URL` in `frontend/admin/.env.local` before building:

```bash
docker compose --profile auth --profile deploy up --build -d
# Set VITE_KEYCLOAK_URL=http://<homelab-ip>:8080 in frontend/admin/.env.local first
```

---

## First-run walkthrough

This section walks through a complete scenario using the seeded demo data so you can see the system end-to-end without needing a real member record. No auth header is needed in development — the backend applies a dev-admin bypass automatically.

### The scenario

`make seed` loads **Jane Smith** — a 25-year Tier I Traditional member at State University of Illinois. The seed covers:

- Member record with certification date, plan choice (Tier I / Traditional), and beneficiary (spouse Robert Smith)
- 25 years of employment + salary history
- Service credit entries spanning both accrual rule periods (pre- and post-September 2024)
- System configuration keys: accrual rules, employment types, leave types

---

### 1 — Explore the API directly

Open `http://localhost:8000/docs` for the interactive Swagger UI. Every endpoint is exercisable from there without any tooling.

**List members:**
```
GET /api/v1/members
```

**Get Jane's member record** (grab her `id` from the list):
```
GET /api/v1/members/{id}
```

**Run a benefit estimate** (retirement date is configurable):
```
GET /api/v1/members/{id}/benefit-estimate?retirement_date=2025-01-15
```

The response includes Final Average Earnings, total service credit, selected formula (General Formula vs Money Purchase), the computed monthly annuity, AAI start date, and the HB2616 minimum floor check. It reflects the full 15-step calculation decision tree.

**Stateless calculation** (no member record lookup — pass all inputs directly):
```
POST /api/v1/calculate/benefit
```
This endpoint is useful for "what-if" estimates and employer-portal integrations. The request body mirrors `BenefitCalculationRequest` in `app/schemas/benefit.py`.

---

### 2 — Admin frontend

Navigate to `http://localhost:5173` after running `pnpm dev` in `frontend/admin/`.

**Members → Jane Smith**

The member detail page shows employment history, salary history, and a benefit estimate form. Enter a retirement date and click Calculate to see the full estimate inline.

**Retirement Cases**

The retirement case workflow demonstrates the approval pipeline:
1. Open a case from the member detail page
2. The system snapshots the benefit calculation at case creation
3. Approve — this locks the calculation, records the benefit election, and transitions Jane's status to `annuitant`
4. Activate — create the first payment record

**Payroll Reports**

Upload a CSV payroll report for Jane's employer. Required columns:

```
member_number,period_start,period_end,gross_earnings,employee_contribution,employer_contribution,days_worked
```

Example row:
```
J-00001,2025-01-01,2025-01-31,7500.00,675.00,1125.00,21
```

After upload the report detail page shows each row's status — `applied`, `skipped` (duplicate), or `error` (member not found, no active employment, missing accrual config). Applied rows write a `ServiceCreditEntry` and a `ContributionRecord` to the ledger.

**API Keys**

The API Keys page lets you create machine-to-machine keys for payroll integrations and employer portal access. The plaintext key is shown once at creation. Keys use the `ofp_` prefix and store only a SHA-256 hash — they are not recoverable.

---

### 3 — System configuration

All fund-specific rules live in the `system_configurations` table as JSONB, looked up by effective date. The seed populates:

| Key | What it controls |
|---|---|
| `service_credit_accrual_rule` | How service credit is computed — `monthly_floor` (post-2024) or `proportional_percent_time` (pre-2024) |
| `employment_types` | Whitelist of valid employment type strings |
| `leave_types` | Whitelist of valid leave type strings |
| `fund_calculation_config` | All benefit calculation parameters (tier cutoffs, FAE windows, formula bands, cap tables, COLA rules) |

To inspect current config values:
```
GET /api/v1/system-configurations
```

Adding a new effective-dated rule (example: switch accrual rule):
```
POST /api/v1/system-configurations
{
  "key": "service_credit_accrual_rule",
  "config_value": {"rule": "monthly_floor"},
  "effective_date": "2024-09-01"
}
```

The calculation engine picks up the most recent config row with `effective_date <= the date being evaluated` — no code changes needed.

---

### 4 — What to configure for a real fund

Before running production data, a fund will need to:

1. **Replace actuarial tables** — CSVs in `data/actuarial_tables/` ship with SURS 2024 Experience Review factors. Swap in your fund's tables.
2. **Seed `fund_calculation_config`** — override only the parameters that differ from SURS defaults. See `app/schemas/fund_config.py` for the full list.
3. **Seed `service_credit_accrual_rule`** — with your fund's rule and effective date(s).
4. **Seed employer records** — one row per contributing employer in `employers`.
5. **Configure `employment_types` and `leave_types`** — match your fund's classifications.
6. **Wire Keycloak** — human-user auth is not yet integrated. The dev bypass must not be used in production.

Fund-specific calculation customization is designed to be configuration, not code: adding a second fund means seeding a new `fund_calculation_config` row with overrides, not forking the engine.

---

## Addons

OpenFlow is designed to be extended. Addons are independently licensed modules — commercial or open — that integrate with the core platform via the addon API. Examples include state-specific reporting formats, integration adapters for payroll vendors, actuarial data import pipelines, and custom portal themes.

Building and selling addons is explicitly permitted under the license.

---

## License

**Apache 2.0 with Commons Clause**

You may use, modify, and deploy this software freely. You may not sell the software itself. Selling implementation services, support, hosting, training, or addons built on this platform is explicitly permitted.

See `LICENSE` for the full text.

---

## Contributing

Contributions are welcome. Before opening a pull request on a significant feature, open an issue to discuss scope and approach. See `CONTRIBUTING.md` for standards, commit conventions, and the module architecture overview.

---

## Status

Early development. Core data model, benefit calculation engine, payroll ingestion, payment disbursement, retirement case workflow, and admin/LOB frontend scaffolding are built. Keycloak JWT auth, member portal, and document generation are not yet started. Not production-ready.

---

*Built by people who've worked in pension administration — not around it.*

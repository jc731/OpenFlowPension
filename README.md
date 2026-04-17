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
| API / backend | Python + FastAPI |
| Database | PostgreSQL |
| Portal frontend | Astro + React |
| Admin UI | React |
| Background jobs | Celery + Redis |
| Document generation | WeasyPrint |
| Auth | Keycloak |
| Actuarial / numerical | NumPy / pandas |

---

## Getting started

```bash
git clone https://github.com/[org]/openflow-pension
cd openflow-pension
cp .env.example .env
docker compose up
```

See `docs/setup.md` for environment configuration, database initialization, and first-run checklist.

---

## Addons

OpenFlow is designed to be extended. Addons are independently licensed modules — commercial or open — that integrate with the core platform via the addon API. Examples include state-specific reporting formats, integration adapters for payroll vendors, actuarial data import pipelines, and custom portal themes.

Building and selling addons is explicitly permitted under the license. See `docs/addon-api.md`.

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

Early development. Core data model and benefit calculation engine are the current focus. Not production-ready.

---

*Built by people who've worked in pension administration — not around it.*

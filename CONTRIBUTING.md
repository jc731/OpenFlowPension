# Contributing to OpenFlow Pension

Thanks for your interest. This document covers how to set up a dev environment, what's expected of contributions, and how the project is organized.

---

## Dev environment

See the [Getting started](README.md#getting-started) section in the README. The short version:

```bash
git clone https://github.com/jc731/OpenFlowPension
cd OpenFlowPension
cp .env.example .env
make up && make migrate && make seed
```

The API is at `http://localhost:8000/docs`. The admin frontend is at `http://localhost:5173` after running `pnpm dev` in `frontend/admin/`.

---

## Before you build

For bug fixes and small improvements, open a PR directly.

For significant new features, open a GitHub Discussion first to align on scope and approach before writing code. The [backlog](docs/BACKLOG.md) documents deferred features with design notes on what to discuss before building — if what you want to build is there, start by reading that section.

The project has a deliberate "don't build speculatively" discipline: fund-specific features that no current fund has requested are deferred intentionally, not forgotten. Check the backlog before assuming something is an oversight.

---

## Branches and commits

Branch names: `feature/short-description`, `fix/short-description`, `docs/short-description`.

Commit messages: imperative mood, sentence case, ~50 character subject line. The subject should complete the sentence "If applied, this commit will ___."

```
# Good
Add employer billing reconciliation endpoint
Fix payroll row flagging when validation_warnings is null
Update ARCHITECTURE.md with billing module detail

# Avoid
added billing stuff
WIP
fixed the bug
```

A commit body is optional. Use it when the *why* is non-obvious — a hidden constraint, a workaround for a specific behavior, a decision that would surprise a reader. Skip it when the subject line is self-explanatory.

---

## Testing

Every new service function needs at least one test in `tests/`. The test suite is service-level: it tests business logic directly against a real (test) database, not against mocked dependencies.

```bash
make test                              # full suite
pytest tests/test_billing_service.py  # single file
```

`tests/test_smoke.py` catches router registration errors and PDF rendering failures that the service-level suite can't see — it must pass after any router or template change.

For the testing patterns used in this project (async helpers, session fixture), see [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md#testing-patterns).

CI runs the full suite on every push via GitHub Actions. A PR is not mergeable if CI is red.

---

## The four hard invariants

These are non-negotiable. Violations introduce data integrity bugs that are very hard to recover from in a production pension system.

**1. Append-only ledgers.** Never `UPDATE` or `DELETE` rows in `service_credit_entries`, `salary_history`, `contribution_records`, or `payment_deductions`. Corrections are a new row that voids the original. New rows only.

**2. Config service for fund rules.** Never hardcode fund-specific values (rates, thresholds, tier cutoffs, formula parameters). Use `get_config(key, as_of, session)` from `app/services/config_service.py`. If the key doesn't exist it raises `ConfigNotFoundError` — that's intentional.

**3. Fernet encryption for PII.** SSNs and bank account numbers are encrypted at the application layer via `app/crypto.py`. Never expose `*_encrypted` fields in API responses or logs.

**4. No ORM cascades on financial tables.** No `cascade="all, delete"` on relationships involving ledger or history tables. Data is never deleted.

---

## Adding a module

The project has a consistent three-layer pattern: model → service → router. See [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) for the full step-by-step checklist, including model conventions, router registration, Alembic migrations, and the documentation updates required when adding a module.

---

## Where things live

| Document | Purpose |
|---|---|
| `CLAUDE.md` | Commands, invariants, module index, auth model — start here |
| `docs/ARCHITECTURE.md` | Detailed per-module documentation |
| `docs/DEVELOPER_GUIDE.md` | How to add a module, config key recipe, testing patterns |
| `docs/BACKLOG.md` | Deferred features with design notes |
| `tests/USER_STORIES.md` | Story-level coverage map |

# Beta Plan

Road to a staff-facing pilot beta: fund office staff running realistic workflows through the admin UI against seeded or migrated data. A member-facing beta (member portal) is a separate later phase and does not block this one.

Story IDs reference `tests/USER_STORIES.md` (91 BUILT / 7 PARTIAL / 5 STUB / 63 GAP as of 2026-06-10). The backend is essentially feature-complete for core administration; the gap between here and beta is admin UI coverage, member-record basics, operational reports, and CI.

---

## Phase 0 — Hardening (done 2026-06-10)

- [x] Fix API boot failure — four routers (`third_party_entities`, `service_purchase`, `net_pay`, `documents`) imported nonexistent `get_db` from `app.api.deps`; standardized on `get_session` from `app.database`
- [x] Fix PDF rendering in the container — WeasyPrint system libraries (pango/gobject/harfbuzz) added to Dockerfile; `pydyf` pinned to 0.10.* (WeasyPrint 62 breaks with pydyf ≥ 0.11)
- [x] Smoke tests (`tests/test_smoke.py`) — app boot via TestClient (catches router import errors the service-level suite can't see), OpenAPI schema build, real WeasyPrint render
- [x] GitHub Actions CI (`.github/workflows/ci.yml`) — backend job (Postgres 16 service, alembic upgrade, full pytest) + frontend job (pnpm build)

**Why this phase existed:** the service-level test suite (338 tests) never imports `app.main` and injects a stub PDF renderer, so the API could fail to boot and PDF generation could be broken at runtime while every test passed. The smoke tests close both blind spots; CI makes the whole suite run on every push.

---

## Phase 1 — Member record basics

Staff can't run a pilot if they can't find members or maintain their contact details, and a pilot fund's membership can't be keyed in one POST at a time.

- [ ] **Address CRUD** (US-M04) — `MemberAddress` model exists; add endpoints + service; wire into document context providers (they reference address fields that are currently never populated via API)
- [ ] **Contact CRUD** (US-M05) — `MemberContact` model exists; add endpoints + service
- [ ] **Member search/filter** (US-M10) — `GET /members` query params: status, employer, employment type, name; paginate
- [ ] **Bulk member import** (US-M09) — CSV import endpoint mirroring the payroll CSV intake pattern (partial-success, row-level errors)

## Phase 2 — Admin UI buildout

Largest chunk of beta work. Backend APIs exist for all of these; the pages don't. Sequenced by staff daily-use frequency:

- [ ] **Beneficiaries & survivor elections** (US-UI10) — beneficiary CRUD, bank accounts, benefit elections
- [ ] **Payment disbursement** (US-UI11) — view/create payments, apply net pay
- [ ] **Service purchase** (US-UI08) — quotes, claim lifecycle, payment recording
- [ ] **Employer billing** (US-UI09) — invoices, payments, deficiency bills
- [ ] **Document generation** (US-UI12) — generate/download member letters
- [ ] **Third-party entities** (US-UI14) — payee management
- [ ] **System config editing** (US-UI13) — config page is currently view-oriented; add guarded editing
- [ ] Surface Phase 1 features in the UI: member search on MemberList, address/contact on MemberDetail

## Phase 3 — Minimum reports (US-RP01–05)

- [ ] **Contribution reconciliation** (US-RP01) — employer/employee contributions by employer over a date range
- [ ] **Delinquency report** (US-RP02) — employers with invoices past due
- [ ] **Membership counts** (US-RP03) — active/terminated/annuitant counts at a date
- [ ] **Annuitant export** (US-RP04) — annuitants with monthly payment amounts
- [ ] **1099-R batch export** (US-RP05) — defer until approaching a year-end with live payments

## Beta entry checklist

- [ ] Phases 1–2 complete; Phase 3 at least RP01 + RP02
- [ ] Pilot fund's `system_configurations` reviewed (incl. `concurrent_employment_max_annual_credit`, required at go-live)
- [ ] Keycloak realm configured for pilot staff (no dev bypass — `environment` ≠ development)
- [ ] Pilot data loaded via bulk import; seed walkthrough (`scripts/seed_mvp.py`) retired for the pilot instance
- [ ] Backup story for the Postgres instance

## Explicitly out of scope for this beta

Member portal (US-MP01–08, architecture undecided) · async payroll (US-P10, only matters >1,000-row files) · refund-repayment calc method (US-SP07) · form ingest (US-DG10) · legacy W-4P · disability module · everything else in `docs/BACKLOG.md`.

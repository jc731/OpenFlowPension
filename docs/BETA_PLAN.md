# Beta Plan

Road to a staff-facing pilot beta: fund office staff running realistic workflows through the admin UI against seeded or migrated data. A member-facing beta (member portal) is a separate later phase and does not block this one.

Story IDs reference `tests/USER_STORIES.md` (see its summary table for current counts). The backend is essentially feature-complete for core administration; the gap between here and beta is admin UI coverage, member-record basics, operational reports, and CI.

---

## Phase 0 — Hardening (done 2026-06-10)

- [x] Fix API boot failure — four routers (`third_party_entities`, `service_purchase`, `net_pay`, `documents`) imported nonexistent `get_db` from `app.api.deps`; standardized on `get_session` from `app.database`
- [x] Fix PDF rendering in the container — WeasyPrint system libraries (pango/gobject/harfbuzz) added to Dockerfile; `pydyf` pinned to 0.10.* (WeasyPrint 62 breaks with pydyf ≥ 0.11)
- [x] Smoke tests (`tests/test_smoke.py`) — app boot via TestClient (catches router import errors the service-level suite can't see), OpenAPI schema build, real WeasyPrint render
- [x] GitHub Actions CI (`.github/workflows/ci.yml`) — backend job (Postgres 16 service, alembic upgrade, full pytest) + frontend job (pnpm build)

**Why this phase existed:** the service-level test suite (338 tests) never imports `app.main` and injects a stub PDF renderer, so the API could fail to boot and PDF generation could be broken at runtime while every test passed. The smoke tests close both blind spots; CI makes the whole suite run on every push.

---

## Phase 1 — Member record basics (done 2026-06-10)

Staff can't run a pilot if they can't find members or maintain their contact details, and a pilot fund's membership can't be keyed in one POST at a time.

- [x] **Address CRUD** (US-M04) — GET/POST `/members/{id}/addresses`; new address end-dates the active one of the same type, which populates the address fields the document context providers read
- [x] **Contact CRUD** (US-M05) — GET/POST `/members/{id}/contacts`; multiple active per type, `supersede` flag for replacement, primary demotion
- [x] **Member search/filter** (US-M10) — `GET /members` query params: status, employer_id, employment_type, q (name/member number), limit/offset
- [x] **Bulk member import** (US-M09) — `POST /members/import` CSV upload mirroring the payroll intake pattern (partial success, row-level errors)

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

### Flagged in UI screenshot review (2026-06-12)

Reviewed all 9 admin pages at 1920×1080 and 1280×800 with seeded data. Layout holds up at both sizes — no overflow or clipping anywhere. Functional/content flags to fold into Phase 2 (not yet fixed):

- [ ] Dashboard "Total Members" shows the length of a `limit: 5` fetch (displays 5 when 9 exist) — needs a count/stats endpoint
- [ ] "Plan" column (member list) and "Plan Choice" card (member detail) show lock state (Open/Locked), never the actual plan tier/type names
- [ ] Member detail "Member Since" displays `created_at` (record import date) — misleading; should be certification or first hire date
- [ ] Status vocabulary drift: seed script sets Jane to `retired`, contract service uses `annuitant`; badges render raw snake_case (`on_leave`)
- [ ] PayrollDetail has no badge mapping for `flagged` rows — they fall back to "Pending" (actively misleading); row `validation_warnings` never displayed
- [ ] Member list search is client-side over the ≤100 fetched rows — wire it to the new server-side `q`/`status`/`employer_id` params
- [ ] Retirement Cases list shows truncated case UUID but no member name/number — staff can't tell whose case it is (list endpoint needs a member join)
- [ ] API Keys page has no empty-state message (blank table body); empty states inconsistent across pages
- [ ] System Config page is a hardcoded key list with descriptions only — no actual values from the DB, no editing (US-CF04/US-UI13)
- [ ] `make seed` doesn't seed `employment_types`/`leave_types` (CLAUDE.md claims it does) — hiring via API fails on a fresh dev environment; backfilled manually in the dev DB

Dev-mode breakage found and **fixed** during this review (commit `e001b91`): trailing-slash 307s emptying every list page in dev, Vite proxy shadowing the `/api-keys` SPA route, `GET /payroll-reports` 500 (lazy-load), missing `GET /retirement-cases` endpoint, and `uuid.UUID(principal["id"])` crashes under the dev-bypass principal (now `principal_uuid()` in deps).

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

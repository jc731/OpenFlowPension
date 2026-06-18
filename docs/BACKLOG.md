# Backlog

Deferred features — not yet implemented. Do not build speculatively; implement when a fund requests it.

---

## Legacy W-4P support

The engine implements the 2020+ redesigned W-4P only. Pre-2020 form used withholding allowances × per-allowance dollar amount.

**When relevant:** Funds with members who filed before 2020 and haven't refiled.

**What to implement:**
- Add `allowances` (int) and `allowance_year` fields to `TaxWithholdingElection` + `NetPayTaxElectionInput` / `TaxWithholdingRequest`
- Seed `federal_withholding_allowance_amounts` in `system_configurations` keyed by year (IRS-published per-allowance amount)
- In `_federal_formula_steps()`: when `allowances > 0`, subtract `allowances × allowance_amount` from annualized income (replaces line 1g deduction)
- Add `form_version: "pre2020" | "2020+"` discriminator column — the two forms cannot coexist on one row

---

## Disability benefit module

High complexity; rules vary significantly by fund. Do not implement speculatively.

**Two types:** ordinary (non-occupational, ~50% of final salary) and duty (occupational, ~75%).

**Key pieces:** eligibility rules (service years, age, medical cert) in `system_configurations` · benefit % of salary at onset (not FAE) · workers' comp offset via `DeductionOrder(deduction_type="workers_compensation")` · annual recertification flag on `disability_claims` table · recovery back to active employment.

**Complex transitions:**
- Disability → regular retirement (auto at normal retirement age)
- Disability → disability retirement (after 3–5 year qualifying period + continued cert; different formula)

**WC integration tiers:** manual (staff entry) → employer payroll column → state WC board API/SFTP.

**Data model sketch:** `disability_claims` table · new member status `disability` · new payment type `disability_benefit`.

---


## Async payroll processing

For large files (>1,000 rows): route creates `PayrollReport(status=pending)` → enqueue Celery task with `report_id` → return 202. Celery task fetches report, processes rows, updates counts, sets `status=completed`.

Redis broker already in docker-compose. Implement when employers submit production volumes.

---

## Contribution interest crediting

Periodic process to credit interest on `contribution_records` for Money Purchase C&I accumulation. Read contributions, apply rate tables from `system_configurations`, write interest entries back. Crediting frequency and compounding rules differ by fund. Defer until Money Purchase is in active use.

---

## Routing number validation

Validate ABA routing numbers against the Federal Reserve EPRD (downloadable CSV of valid routing numbers). Check Fedwire eligibility for wire payments. Implement as a pre-save hook in `bank_account_service.add_bank_account`. Low priority until payment processing is live.

---

## Party model refactor

**Trigger:** when employer contacts are added (first non-member, non-beneficiary person type).

**Plan:** Extract shared `parties` table (`party_type`, name, DOB, SSN, etc.); replace inline demographics in `members` and `beneficiaries` with `party_id` FK. `Beneficiary.linked_member_id` → `Beneficiary.party_id`. `Member` gets its own `party_id`.

`linked_member_id` is the interim bridge — handles the most common case (beneficiary who is also a member) without requiring the full refactor now.

---

## Unimplemented benefit calc items

- FAE Method B (48-month actual, for 12-month contract staff)
- Part-time adjustments (Spec §3.5)
- Reciprocal service benefit apportionment
- PEP calculation (Spec §13)
- HAE earnings limitation (Spec §11)
- Income tax exclusion (Spec §10)

---

## Leave purchase / buy-back

The service purchase infrastructure (claims, payment ledger, entry_type routing) is designed to support purchased leave credit (e.g., buying back unpaid leave, sabbatical, parental leave taken before system coverage). Deferred — implement when a fund requests it.

**What's already in place:** `service_purchase_claims` tracking, `service_purchase_payments` ledger, `credit_type_slot` routing in `service_purchase_types` config, and the `ServiceCreditEntry.entry_type` free-string convention all support a `leave_buyback` type without schema changes. The main addition would be a `leave_buyback` calc method and the appropriate `credit_type_slot` mapping.

---

## Document generation architecture — component model

The current `CONTEXT_PROVIDERS` / `EXPLICIT_ASSEMBLERS` framework handles single-document generation well, but lacks a composable template layer. Before building more templates, align on the component model.

**Architectural discussion needed (do not build speculatively):**

The proposed model, by analogy to Astro SSG:
- **Templates** = the outer shell (header, footer, fund branding, page layout). Per-document-type, versioned.
- **Data widgets** = named content slots (e.g., `<MemberDemographicsBlock>`, `<ServiceCreditSummary>`, `<BenefitEstimateTable>`). Each widget owns a `context_key` that maps to a `CONTEXT_PROVIDER`.
- **Expandable components** = conditional sections that appear based on data presence or request params (e.g., beneficiary table only if beneficiaries exist, QILDRO section only if an active order exists).

Questions to resolve before building:
1. Template format: WeasyPrint HTML+CSS vs Jinja2 macro composition vs a thin Python DSL. WeasyPrint is already integrated but lacks component reuse.
2. Widget registration: extend `CONTEXT_PROVIDERS` with a `widgets` namespace, or a separate registry?
3. Versioning: when a template changes, do in-flight `GeneratedDocument` records point to the old version? Need a `template_version` field on `generated_documents`.
4. Preview vs final: separate rendering paths or same path with a `draft=true` flag?

---

## Form submission ingest

The `form_submissions` table and `FormSubmission` model already exist (stubbed alongside the document generation framework). The table tracks the sent → returned lifecycle with `return_data` JSONB and `status`: sent | returned | ingested | expired | cancelled.

**What's missing:** The ingest path — parsing a returned form's data, validating fields, and writing the appropriate records (election changes, address updates, etc.) back to the member record. This is tightly coupled to specific form types and should be built per-form when a fund requests e-form processing.

**Design note:** Each ingestable form type will likely need a dedicated parser that maps `return_data` keys to the appropriate service calls (e.g., a returned W-4P form → `TaxWithholdingElection` row). Consider a registry pattern analogous to `CONTEXT_PROVIDERS`.

---

## Self-service portals (ESS + MSS)

Two separate frontends, both driven 100% by the existing REST API. Neither portal owns any business logic — they are pure consumers of the API and must remain severable (replaceable by any other portal, or by a third-party integration, without backend changes).

**Employer Self-Service (ESS):** Employer-facing portal for submitting new hires, terminations, payroll reports, and demographic updates. The underlying API endpoints already exist (hire, terminate, payroll upload, member search). ESS is an authenticated employer-scoped view over them with appropriate `employment:write` / `payroll:write` scope. Can be the existing admin frontend with employer-restricted auth, or a separate SPA.

**Member Self-Service (MSS):** Member-facing portal. Key self-service surfaces: benefit estimate, service credit history, payment history, address/contact update, beneficiary designation, tax withholding election (W-4P), document download, retirement scheduling. All backed by existing API endpoints — no new backend work required for basic MSS. Member auth via Keycloak with a member-scope role (narrower than fund staff).

**Architecture principle:** Both portals must call the API exclusively — no direct DB access, no shared server-side logic. This keeps them replaceable and allows the same API to power third-party integrations (HR systems, payroll providers) without code changes.

**Prioritize MSS after:** retirement case workflow is stable and at least one live fund is in pilot.

---

## Return to Work (RTW) — affected annuitant + FAE billing

When an annuitant returns to covered employment, two different rules apply depending on annuitant sub-type:

- **Affected annuitant:** annuity is NOT paused. Employer is billed for the RTW employment. FAE billing fires separately if the RTW salary exceeds the original FAE threshold (salary spike billing against the employer).
- **Re-retiree:** different RTW rules (annuity may be paused, no FAE billing).

**What's needed:**
- New `annuitant_type` field on the member or a new RTW employment record flag (`rtw_affected` boolean on `EmploymentRecord`).
- RTW hire path in `contract_service` that allows hiring an annuitant without raising the current "already annuitant" block — the block should only prevent a new *retirement case*, not a new employment record.
- RTW billing workflow in `billing_service`: fire an employer invoice when an affected annuitant is hired; a separate invoice type for FAE spike billing when RTW salary exceeds the member's original FAE.
- Config keys for RTW earnings thresholds and billing rate.

**Belongs under:** employer billing module.

---

## PLSR — Portable Lump Sum Retirement path

PLSR is a retirement option available to Portable plan members: at retirement, the member receives a lump sum representing the portable (employee-contributed) portion of their account alongside a reduced ongoing monthly annuity. It is not a full lump sum exit — it is a split-disbursement retirement.

The `lump_sum` benefit option type is registered in the calculator but currently stubs back to `single_life`. PLSR is the correct named path.

**What's needed:**
- `benefit_option_type = "plsr"` as a valid option in the retirement case (alongside `single_life`, `reversionary`, `js_*`).
- PLSR calculation: determine the portable account balance (employee contributions + credited interest); compute the residual monthly annuity on the employer-funded portion; return both amounts in `BenefitOptionResult`.
- Two payment disbursements at retirement activation: one-time PLSR lump sum + first recurring annuity payment.
- `RetirementCase.plsr_lump_sum_amount` field (or store in `calculation_snapshot` JSONB — no schema change required if using snapshot).
- Disbursement form template for the PLSR payout.

**Design note:** PLSR availability should be gated on `plan_type == "portable"` — raise `ValueError` otherwise (matching the existing J&S gate pattern).

---

## RSP (Defined Contribution) plan type + supplemental DC

RSP (Retirement Savings Plan) is a defined-contribution plan variant where member contributions go to an external investment provider (Voya) rather than the fund's defined-benefit pool. This is architecturally different from Traditional and Portable plans.

Two distinct use cases:
1. **RSP as primary plan:** member elects RSP at enrollment instead of Traditional/Portable. All contributions route to Voya via SPARK (a payroll contribution interface). Retirement is either an annuitized exit (Voya manages the annuity stream) or a non-annuitized lump sum distribution.
2. **Supplemental DC:** regular DB plan member contributes additionally to a DC account (supplemental savings alongside the defined-benefit pension).

**What's needed for RSP primary:**
- New `plan_type = "rsp"` in `plan_choice_service` (currently only `traditional` / `portable` accepted).
- RSP part account entity (separate from `contribution_records` — tracks Voya account balance, not fund-held contributions).
- SPARK file exchange: outbound contribution file to Voya each payroll cycle (fixed-format or API); inbound balance confirmation. Likely a Celery task.
- RSP termination workflow: SPARK contribution drops to $0; termination record created; no separation refund path (member goes directly to Voya for distribution).
- RSP retirement paths:
  - Annuitized: Voya manages ongoing annuity; the fund records the annuitization event.
  - Non-annuitized: Voya distributes lump sum; member status → inactive; no ongoing fund annuity stream.
- Blocked rehire: if `plan_type == "rsp"` and `member_status == "annuitant"`, reject any new hire into fund-covered employment.
- Death benefit: depends on election at enrollment (remaining account balance to beneficiary vs continued annuity to survivor).

**Design note:** RSP is substantial enough to warrant its own service module (`app/services/rsp_service.py`) and models. Do not bolt onto existing `service_purchase` or `payment` tables.

---

## QILDRO — Qualified Illinois Domestic Relations Order

A QILDRO is a court order — issued in divorce proceedings — that entitles an ex-spouse (the "alternate payee") to a share of the member's pension. It is NOT a third-party deduction order (like a union dues deduction to a `ThirdPartyEntity`). The alternate payee receives their share as an independent payment stream, effectively a pseudo-annuity derived from the member's benefit.

**Conceptual model:**
- The QILDRO reduces the member's annuity by the court-ordered percentage or fixed amount.
- The alternate payee receives the carved-out portion as their own recurring payment.
- The alternate payee is more like a pseudo-member than a third-party entity — they have their own bank account, their own 1099-R, and survive the member's death up to the terms of the order.

**What's needed:**
- `QILDROOrder` model: links member → alternate payee; stores court order reference, effective date, expiration/end condition, calculation method (percentage of benefit vs fixed amount), and status (active / terminated / expired).
- Alternate payee record: can reuse `Beneficiary` extended with an `alternate_payee` type, or a lightweight `AlternatePayee` entity (name, DOB, SSN, bank account). The pseudo-member approach is cleaner than reusing `Beneficiary` — consider adding `alternate_payee_type` to the beneficiary model.
- Benefit calculation impact: `calculate_benefit()` must accept active QILDROs and reduce the member's annuity accordingly. Store the pre- and post-QILDRO amounts in `RetirementCase.calculation_snapshot`.
- Payment split at disbursement: when a member payment is issued, generate a corresponding alternate payee payment for the QILDRO share (append-only, same ledger pattern as `PaymentDeduction` but routes to a separate payee).
- Death handling: on member death, QILDRO terms determine whether alternate payee continues receiving payments, receives a lump sum, or the order terminates. Needs a `qildro_death_treatment` field on the order.
- 1099-R: alternate payee receives their own 1099-R for their share (same as a regular annuity recipient).

**Relationship to existing models:** `DeductionOrder.source_document_type = "court_order"` exists for routing garnishments to a `ThirdPartyEntity`, but QILDRO is structurally different — the alternate payee has ongoing rights and needs their own payment record, not a deduction off the member's net pay to a payee org.

---

## Survivor benefit gaps

- Contingent beneficiary fallback (if primary predeceased)
- Plan-configurable lump sum continuation periods

Defer until first fund goes live.

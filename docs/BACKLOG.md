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

## Service purchase — refund_repayment calc method

The `refund_repayment` calc method is stubbed and raises `ValueError`. Refund repayment cost = original refund amount + compound interest from refund date to repayment date at a fund-specific rate.

**What's needed:**
- Source the original refund amount — either from a `ContributionRecord(contribution_type="refund")` record (if the refund was processed in-system) or from manual staff entry on the claim (`params.original_refund_amount`)
- Compound interest formula: `cost = original × (1 + rate)^years` where `rate` comes from `interest_rate` in the type config
- Partial-year handling (day-count convention)

Implement in `_calc_refund_repayment()` in `service_purchase_service.py`. No schema changes needed — `cost_breakdown` JSONB captures the full calculation.

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

## Form submission ingest

The `form_submissions` table and `FormSubmission` model already exist (stubbed alongside the document generation framework). The table tracks the sent → returned lifecycle with `return_data` JSONB and `status`: sent | returned | ingested | expired | cancelled.

**What's missing:** The ingest path — parsing a returned form's data, validating fields, and writing the appropriate records (election changes, address updates, etc.) back to the member record. This is tightly coupled to specific form types and should be built per-form when a fund requests e-form processing.

**Design note:** Each ingestable form type will likely need a dedicated parser that maps `return_data` keys to the appropriate service calls (e.g., a returned W-4P form → `TaxWithholdingElection` row). Consider a registry pattern analogous to `CONTEXT_PROVIDERS`.

---

## Member portal frontend

Separate frontend from the admin/LOB app. Architecture undecided (Astro, Vite, etc.) — evaluate when feature scope is clearer.

---

## Survivor benefit gaps

- Contingent beneficiary fallback (if primary predeceased)
- Plan-configurable lump sum continuation periods

Defer until first fund goes live.

# OpenFlow Pension — User Stories

Organized by persona and domain. Used to identify coverage gaps and prioritize build work.

**Status tags:**  
`[BUILT]` — implemented and tested  
`[PARTIAL]` — partially implemented; gaps noted  
`[STUB]` — scaffolded but not functional  
`[GAP]` — not yet built  

**Personas:**  
- **Fund Staff** — pension office staff using the admin/LOB frontend  
- **System Admin** — IT staff who configure the platform  
- **Employer Admin** — HR/payroll contact at a participating employer  
- **Integration** — external system submitting data via API  
- **Member** — pension plan participant  

---

## Member Onboarding & Management

**US-M01** `[BUILT]`  
As **Fund Staff**, I want to create a new member record with demographics (name, DOB, SSN, member number), so that the member is enrolled in the system.  
_Tests: test_contract_service.py_

**US-M02** `[BUILT]`  
As **Fund Staff**, I want to look up a member by member number or ID, so that I can view their full record.  
_Tests: test_contract_service.py_

**US-M03** `[BUILT]`  
As **Fund Staff**, I want to view a member's current status (active, on\_leave, terminated, annuitant, deceased, inactive), so that I know where they are in their lifecycle.  
_Tests: test_contract_service.py_

**US-M04** `[PARTIAL]`  
As **Fund Staff**, I want to view and update a member's mailing address, so that correspondence reaches them.  
_Gap: MemberAddress model exists but no address CRUD endpoints or admin page; document context provider references address fields but they aren't populated via API._

**US-M05** `[PARTIAL]`  
As **Fund Staff**, I want to record a member's contact information (phone, email), so that we can reach them.  
_Gap: MemberContact model exists; no CRUD endpoints surfaced._

**US-M06** `[BUILT]`  
As **Fund Staff**, I want to set a member's plan tier and plan type (plan choice), so that the correct benefit formula applies to them.  
_Tests: test_plan_choice_service.py_

**US-M07** `[BUILT]`  
As **Fund Staff**, I want to lock a member's plan choice once the election window closes, so that the elected plan cannot be changed.  
_Tests: test_plan_choice_service.py_

**US-M08** `[BUILT]`  
As **Fund Staff**, I want to record the member's certification date (hire date for benefit eligibility), so that tier determination and retirement eligibility is accurate.  
_Tests: test_benefit_calculator.py, test_benefit_estimate_service.py_

**US-M09** `[GAP]`  
As **Fund Staff**, I want to bulk-import a list of new members from a CSV or spreadsheet, so that I don't have to create them one at a time during onboarding.  
_Gap: No bulk import endpoint or service function. Single-row API only._

**US-M10** `[GAP]`  
As **Fund Staff**, I want to search and filter the member list by status, employer, employment type, or name, so that I can find members without scrolling through everything.  
_Gap: `GET /members` returns all; no filter/search parameters._

**US-M11** `[GAP]`  
As **Fund Staff**, I want to see a complete activity timeline for a member (employment changes, salary adjustments, payroll posts, service purchase events, retirement case steps), so that I have a full audit trail in one place.  
_Gap: Each ledger is queryable individually but no unified timeline view or endpoint._

---

## Employment & Contract Management

**US-E01** `[BUILT]`  
As **Fund Staff**, I want to record a new hire event (employer, employment type, hire date, percent time, starting salary), so that the member's employment record is established.  
_Tests: test_contract_service.py_

**US-E02** `[BUILT]`  
As **Fund Staff**, I want to record a termination date for an employment, so that service credit accrual stops correctly.  
_Tests: test_contract_service.py_

**US-E03** `[BUILT]`  
As **Fund Staff**, I want to record a leave of absence (leave type, start date), so that the period is tracked for eligibility purposes.  
_Tests: test_contract_service.py_

**US-E04** `[BUILT]`  
As **Fund Staff**, I want to close a leave period (end date), so that the member returns to active status.  
_Tests: test_contract_service.py_

**US-E05** `[BUILT]`  
As **Fund Staff**, I want to change a member's percent-time employment, optionally recording a simultaneous salary change, so that both records stay in sync.  
_Tests: test_contract_service.py_

**US-E06** `[BUILT]`  
As **Fund Staff**, I want to record a salary change (new annual salary, effective date), so that benefit calculations use the correct FAE figure.  
_Tests: test_contract_service.py_

**US-E07** `[PARTIAL]`  
As **Fund Staff**, I want to view the full salary history for a member in reverse-chronological order, so that I can trace FAE inputs.  
_Gap: SalaryHistory is loaded by benefit_estimate_service internally; no dedicated salary history list endpoint._

**US-E08** `[GAP]`  
As **Fund Staff**, I want the system to warn me when a member's combined service credit from concurrent employments exceeds the plan maximum in a year, so that over-crediting is prevented.  
_Gap: `concurrent_employment_max_annual_credit` config key exists but is not enforced at payroll ingestion. Required at go-live._

**US-E09** `[GAP]`  
As **Fund Staff**, I want to record a member's death and have all active employer records closed automatically, so that no further payroll posts or benefit payments are processed.  
_Gap: `record_death` sets member\_status=deceased and blocks writes, but does not auto-close open EmploymentRecords or pending BenefitPayments._

**US-E10** `[PARTIAL]`  
As **Fund Staff**, I want to view a list of all current employers and their active member counts, so that I can manage fund membership by employer.  
_Gap: Employer CRUD endpoints exist; no member-count summary or employer dashboard._

---

## Payroll Submission & Validation

**US-P01** `[BUILT]`  
As **Employer Admin**, I want to submit a payroll report as a JSON batch (member number, period, gross earnings, contributions, days worked), so that member contributions are recorded for the period.  
_Tests: test_payroll_service.py_

**US-P02** `[BUILT]`  
As **Employer Admin**, I want to upload a payroll CSV file, so that I don't need to build an API integration to submit payroll.  
_Tests: test_payroll_service.py_

**US-P03** `[BUILT]`  
As **Employer Admin**, I want the system to validate that my submitted rows pass basic structural checks (valid dates, non-negative amounts), so that obviously bad data is rejected with a clear error message.  
_Tests: test_payroll_validation_service.py_

**US-P04** `[BUILT]`  
As **Employer Admin**, I want the system to flag rows where gross earnings or days worked exceed fund-defined thresholds, so that I can review anomalies before they are posted.  
_Tests: test_payroll_validation_service.py_

**US-P05** `[BUILT]`  
As **Employer Admin**, I want the system to warn me when submitted contribution amounts are below the authoritative rate for an employee, so that I can catch payroll calculation errors before a deficiency invoice is generated.  
_Tests: test_billing_service.py, test_payroll_service.py_

**US-P06** `[BUILT]`  
As **Employer Admin**, I want partial payroll submissions to succeed — valid rows applied, errored rows flagged — without blocking the whole batch, so that one bad row doesn't hold up the rest.  
_Tests: test_payroll_service.py_

**US-P07** `[BUILT]`  
As **Employer Admin**, I want to view the status of a submitted payroll report (applied, error, skipped, flagged counts plus per-row detail), so that I can identify and resolve issues.  
_Tests: test_payroll_service.py_

**US-P08** `[BUILT]`  
As **Fund Staff**, I want duplicate submissions for the same member/period to be silently skipped, so that re-uploading a payroll file doesn't double-post contributions.  
_Tests: test_payroll_service.py_

**US-P09** `[GAP]`  
As **Fund Staff**, I want to void and resubmit a payroll row for a specific member/period, so that correction entries can be made after a report is completed.  
_Gap: ContributionRecord has a void pattern (voided\_at/by) but no endpoint or service function to void a specific row and re-process it._

**US-P10** `[STUB]`  
As **Integration**, I want large payroll files (1,000+ rows) to be processed asynchronously, returning a report ID immediately, so that my API call doesn't time out.  
_Gap: Celery + Redis scaffolded; no task implemented. Backlog item._

**US-P11** `[GAP]`  
As **Fund Staff**, I want to configure the fund validation thresholds (max gross, max days, contribution rate tolerance, reject vs. warn mode) via the admin UI, so that I don't need a database migration to adjust policy.  
_Gap: Config seeded via scripts; system config admin UI is read-only placeholder._

**US-P12** `[GAP]`  
As **Fund Staff**, I want to view all payroll reports across all employers in one list with filtering by status and date range, so that I can monitor submission compliance.  
_Gap: `GET /payroll-reports` exists with optional employer\_id filter; no date-range or status filter._

---

## Benefit Calculation & Estimation

**US-B01** `[BUILT]`  
As **Fund Staff**, I want to run a stateless benefit estimate for a member (given retirement date, sick leave days, benefit option), so that I can answer member inquiries without creating a retirement case.  
_Tests: test_benefit_calculator.py, test_benefit_estimate_service.py_

**US-B02** `[BUILT]`  
As **Fund Staff**, I want the benefit estimate to pull the member's current salary history, service credit, and contributions automatically, so that I don't have to manually enter data.  
_Tests: test_benefit_estimate_service.py_

**US-B03** `[BUILT]`  
As **Fund Staff**, I want the benefit estimate to apply the correct formula (General, Money Purchase, Police/Fire) based on the member's plan type, so that the result is formula-appropriate.  
_Tests: test_benefit_calculator.py_

**US-B04** `[BUILT]`  
As **Fund Staff**, I want the estimate to support all benefit options (single life, J&S 50/75/100, reversionary) and show the monthly annuity for each, so that I can advise the member on option selection.  
_Tests: test_benefit_calculator.py_

**US-B05** `[BUILT]`  
As **Fund Staff**, I want to understand why a member is ineligible for retirement (insufficient service credit, wrong age, wrong tier), so that I can advise them on what they need.  
_Tests: test_benefit_calculator.py_

**US-B06** `[BUILT]`  
As **Fund Staff**, I want the benefit calc engine to be parameterized by fund configuration, so that multiple funds with different formula details can use the same engine.  
_Tests: test_fund_config_service.py_

**US-B07** `[GAP]`  
As **Fund Staff**, I want to model a member's benefit at multiple retirement dates side-by-side, so that I can show them the financial impact of retiring earlier vs. later.  
_Gap: Estimate endpoint handles one date at a time; no multi-scenario compare endpoint._

**US-B08** `[GAP]`  
As **Fund Staff**, I want to see the full FAE calculation detail (which years were selected, daily proration, spike cap application) in the benefit estimate response, so that I can validate and explain the calculation.  
_Gap: FAE result is returned in BenefitCalculationResult but intermediate steps (which salary periods included, spike adjustments) are not fully exposed._

**US-B09** `[GAP]`  
As **System Admin**, I want to configure fund-specific benefit formula parameters (multiplier, FAE window, normal retirement age, COLA type) via the system config UI, so that the platform supports our specific plan document.  
_Gap: FundConfig schema and config key exist; seeded via scripts; no admin UI for editing._

**US-B10** `[GAP]`  
As **Fund Staff**, I want the benefit estimate to account for purchased service credit by type (military, OPE, prior service), so that purchased years are correctly included in the formula.  
_Gap: `_service_credit_by_slot()` routes purchased credit by type into the correct calculation slot (system\_service\_years, military\_service\_years, ope\_service\_years); this is built but not fully validated across all edge cases for type-restricted benefits._

**US-B11** `[GAP]`  
As **Fund Staff**, I want the system to calculate reciprocal service credit from other public pension funds, so that members with cross-fund service are credited correctly.  
_Gap: Not implemented. Backlog item — high complexity._

---

## Retirement Case Processing

**US-R01** `[BUILT]`  
As **Fund Staff**, I want to open a retirement case for a member, capturing their desired retirement date and benefit option, so that the case enters the approval workflow.  
_Tests: test_retirement_service.py_

**US-R02** `[BUILT]`  
As **Fund Staff**, I want to recalculate a draft retirement case (e.g. after a salary correction), so that the snapshot reflects the most current data before approval.  
_Tests: test_retirement_service.py_

**US-R03** `[BUILT]`  
As **Fund Staff**, I want to approve a retirement case, locking the final monthly annuity and recording the member's benefit election, so that the benefit amount is immutably committed.  
_Tests: test_retirement_service.py_

**US-R04** `[BUILT]`  
As **Fund Staff**, I want to activate a retirement case (creating the first annuity payment record), so that disbursement can begin.  
_Tests: test_retirement_service.py_

**US-R05** `[BUILT]`  
As **Fund Staff**, I want to cancel a retirement case before activation, so that a member who changes their mind doesn't end up in the payment queue.  
_Tests: test_retirement_service.py_

**US-R06** `[BUILT]`  
As **Fund Staff**, I want the system to prevent opening a second active retirement case for a member who already has an open one, so that duplicate cases don't exist.  
_Tests: test_retirement_service.py_

**US-R07** `[GAP]`  
As **Fund Staff**, I want to add notes and attach supporting documentation to a retirement case, so that the paper file and digital record stay in sync.  
_Gap: `note` field exists on RetirementCase; no document attachment or note history._

**US-R08** `[GAP]`  
As **Fund Staff**, I want a retirement case to automatically generate a benefit estimate letter and send it to the member's address, so that they receive written confirmation of their projected benefit.  
_Gap: Document generation framework is built; benefit\_estimate\_letter template exists; but no auto-trigger from retirement case creation/approval and no email/mailing integration._

---

## Death & Survivor Benefits

**US-S01** `[BUILT]`  
As **Fund Staff**, I want to record a member's benefit election (option type, monthly amount, beneficiary), so that the survivor path is established.  
_Tests: test_survivor_service.py_

**US-S02** `[BUILT]`  
As **Fund Staff**, I want to retrieve the current benefit election for a member as of a given date, so that I know what applies at the time of death.  
_Tests: test_survivor_service.py_

**US-S03** `[BUILT]`  
As **Fund Staff**, I want to calculate the survivor benefit amount for a member given a death event date, so that I can determine what the beneficiary is entitled to.  
_Tests: test_survivor_service.py_

**US-S04** `[BUILT]`  
As **Fund Staff**, I want to initiate survivor annuity payments for a beneficiary after a member's death, so that the beneficiary begins receiving their entitlement.  
_Tests: test_survivor_service.py_

**US-S05** `[BUILT]`  
As **Fund Staff**, I want the pre-retirement death path to calculate the lump-sum return of employee contributions, so that the estate receives the correct refund.  
_Tests: test_survivor_service.py_

**US-S06** `[GAP]`  
As **Fund Staff**, I want the system to fall back to a contingent beneficiary if the primary beneficiary has predeceased the member, so that the benefit flows to the correct party.  
_Gap: Backlog item. Current implementation requires primary beneficiary._

**US-S07** `[GAP]`  
As **Fund Staff**, I want to configure plan-specific lump-sum continuation periods for certain benefit options, so that survivor benefits are paid for the correct minimum duration.  
_Gap: Backlog item._

**US-S08** `[GAP]`  
As **Fund Staff**, I want to record a beneficiary's death and terminate their survivor annuity payments, so that disbursement stops correctly.  
_Gap: No endpoint or service function for beneficiary death recording or survivor annuity termination._

---

## Beneficiaries & Bank Accounts

**US-BN01** `[BUILT]`  
As **Fund Staff**, I want to add a beneficiary to a member's record (individual, estate, trust, or organization) with their relationship and share percentage, so that the survivor path is established.  
_Tests: test_beneficiary_service.py_

**US-BN02** `[BUILT]`  
As **Fund Staff**, I want to close a beneficiary record when it is no longer current (divorce, death, change of election), so that the record is preserved but inactive.  
_Tests: test_beneficiary_service.py_

**US-BN03** `[BUILT]`  
As **Fund Staff**, I want to add a bank account for a beneficiary (routing + encrypted account number), so that survivor ACH payments can be directed to the correct account.  
_Tests: test_beneficiary_service.py_

**US-BN04** `[BUILT]`  
As **Fund Staff**, I want to mark a beneficiary bank account as the primary disbursement account, so that payments are routed correctly.  
_Tests: test_beneficiary_service.py_

**US-BN05** `[GAP]`  
As **Fund Staff**, I want to validate that a beneficiary's bank routing number is a valid ABA number, so that ACH payments don't fail due to bad routing data.  
_Gap: Routing number validation against EPRD not implemented. Backlog item._

**US-BN06** `[GAP]`  
As **Fund Staff**, I want to link a beneficiary to an existing member record (for the common case where the beneficiary is also a fund member), so that I don't duplicate demographic data.  
_Gap: `linked_member_id` bridge field exists on Beneficiary as an interim solution; full party model refactor is deferred._

---

## Service Purchase

**US-SP01** `[BUILT]`  
As **Fund Staff**, I want to get a cost estimate for a service purchase (military, OPE, prior service), given the member's current salary and the number of years to purchase, so that I can advise the member before they commit.  
_Tests: test_service_purchase_service.py_

**US-SP02** `[BUILT]`  
As **Fund Staff**, I want to create a service purchase claim for a member, freezing the cost calculation at the time of creation, so that the cost doesn't change mid-process.  
_Tests: test_service_purchase_service.py_

**US-SP03** `[BUILT]`  
As **Fund Staff**, I want to move a service purchase claim through its lifecycle (draft → pending approval → approved → in payment → completed), so that the workflow is tracked.  
_Tests: test_service_purchase_service.py_

**US-SP04** `[BUILT]`  
As **Fund Staff**, I want to record an installment payment against a service purchase claim, with the credit automatically granted when the claim is paid in full, so that partial payments are supported.  
_Tests: test_service_purchase_service.py_

**US-SP05** `[BUILT]`  
As **Fund Staff**, I want the system to grant service credit on approval (for types configured that way) rather than waiting for full payment, so that the member's benefit is credited as soon as the obligation is established.  
_Tests: test_service_purchase_service.py_

**US-SP06** `[BUILT]`  
As **Fund Staff**, I want to cancel a service purchase claim at any non-terminal state, with a cancellation reason, so that abandoned claims are tracked.  
_Tests: test_service_purchase_service.py_

**US-SP07** `[STUB]`  
As **Fund Staff**, I want to calculate the cost of repurchasing a prior refund (original refund amount + compound interest), so that members who left and returned can reinstate their prior service.  
_Gap: `refund_repayment` calc method raises ValueError; original refund sourcing + compounding formula not implemented. Backlog item._

**US-SP08** `[BUILT]`  
As **Fund Staff**, I want purchased service credit to flow into the correct benefit formula slot (military years, OPE years, general service years) based on type, so that eligibility and formula calculations are correct.  
_Tests: test_service_purchase_service.py, test_benefit_estimate_service.py_

**US-SP09** `[GAP]`  
As **Fund Staff**, I want to add a new service purchase type (e.g. leave buyback) by adding a config entry without code changes, so that fund-specific purchase types can be added without a deployment.  
_Gap: Infrastructure supports this via config-driven types; leave buyback specifically is deferred. Requires a new `calc_method` if the pricing logic differs._

---

## Employer Billing

**US-BL01** `[BUILT]`  
As **System Admin**, I want to configure fund-wide and employer-specific contribution rates (employee %, employer %) with effective dates, so that the authoritative rates are in the system.  
_Tests: test_billing_service.py_

**US-BL02** `[BUILT]`  
As **System Admin**, I want to configure different rates for specific employment types (e.g. police/fire), so that those members' contributions are validated against the correct rate.  
_Tests: test_billing_service.py_

**US-BL03** `[BUILT]`  
As **Fund Staff**, I want the system to warn me during payroll submission when an employer's submitted contributions are below the authoritative rate, so that I can catch under-remittance early.  
_Tests: test_billing_service.py, test_payroll_service.py_

**US-BL04** `[BUILT]`  
As **Fund Staff**, I want to preview the deficiency amount for one or more payroll reports before creating an invoice, so that I can verify the calculation before issuing a bill.  
_Tests: test_billing_service.py_

**US-BL05** `[BUILT]`  
As **Fund Staff**, I want to generate a deficiency invoice from one or more payroll reports, so that the employer is billed for the shortfall.  
_Tests: test_billing_service.py_

**US-BL06** `[BUILT]`  
As **Fund Staff**, I want to create a supplemental invoice (e.g. UAL assessment, interest charge) for an employer, so that I can bill for amounts not tied to a specific payroll report.  
_Tests: test_billing_service.py_

**US-BL07** `[BUILT]`  
As **Fund Staff**, I want to issue an invoice (transition from draft to issued), so that it is formally sent to the employer.  
_Tests: test_billing_service.py_

**US-BL08** `[BUILT]`  
As **Fund Staff**, I want to record a payment against an invoice, with the invoice automatically marking itself paid when fully settled, so that the payment ledger is maintained.  
_Tests: test_billing_service.py_

**US-BL09** `[BUILT]`  
As **Fund Staff**, I want to void a draft or issued invoice with a reason, so that errors can be corrected without deleting records.  
_Tests: test_billing_service.py_

**US-BL10** `[BUILT]`  
As **Fund Staff**, I want to view all invoices for an employer with status filtering, so that I can track outstanding obligations.  
_Tests: test_billing_service.py_

**US-BL11** `[GAP]`  
As **Fund Staff**, I want the system to automatically mark invoices as overdue when their due date passes without full payment, so that delinquent accounts are flagged.  
_Gap: `overdue` is a defined status on the model but nothing transitions invoices to it. No background job or scheduled check._

**US-BL12** `[GAP]`  
As **Fund Staff**, I want to calculate and apply late payment interest to an overdue invoice, so that the employer is charged the correct penalty.  
_Gap: `interest_accrued` field exists on EmployerInvoice but no service function computes or applies it._

**US-BL13** `[GAP]`  
As **Fund Staff**, I want to batch multiple payroll reports across multiple periods into a single deficiency invoice, so that I can issue one bill for a multi-period shortfall.  
_Gap: `calculate_deficiency` accepts a list of report IDs so batching is technically possible, but there's no UI workflow or endpoint designed for multi-period batch deficiency._

**US-BL14** `[GAP]`  
As **Fund Staff**, I want to generate and send a PDF deficiency notice to the employer, so that they receive a formal written bill.  
_Gap: Document generation framework exists; no billing notice document template created._

---

## Payment Disbursement

**US-PY01** `[BUILT]`  
As **Fund Staff**, I want to create a benefit payment record (annuity, refund, lump sum, etc.) for a member, so that the payment is tracked in the system.  
_Tests: test_payment_service.py_

**US-PY02** `[BUILT]`  
As **Fund Staff**, I want to update the status of a payment (draft → pending → issued → paid), so that the disbursement lifecycle is tracked.  
_Tests: test_payment_service.py_

**US-PY03** `[BUILT]`  
As **Fund Staff**, I want to calculate the net pay for a payment (subtracting deductions and withholding taxes), so that the member receives the correct net amount.  
_Tests: test_net_pay_service.py_

**US-PY04** `[BUILT]`  
As **Fund Staff**, I want to apply the net pay calculation to a payment (persisting deduction rows and updating net_amount), so that the payment is ready for disbursement.  
_Tests: test_net_pay_service.py_

**US-PY05** `[BUILT]`  
As **Fund Staff**, I want to create a standing deduction order for a member (fixed amount or % of gross, to a specific payee), so that recurring deductions are applied automatically.  
_Tests: test_payment_service.py_

**US-PY06** `[BUILT]`  
As **Fund Staff**, I want to close a deduction order by setting its end date, so that it no longer applies to future payments without deleting the history.  
_Tests: test_payment_service.py_

**US-PY07** `[BUILT]`  
As **Fund Staff**, I want to add and manage bank accounts for a member (routing, encrypted account number, checking/savings, primary flag), so that ACH disbursements are routed correctly.  
_Tests: test_payment_service.py_

**US-PY08** `[GAP]`  
As **Fund Staff**, I want to reverse a payment and create a correcting payment, so that errors discovered after disbursement can be corrected with a full audit trail.  
_Gap: `status=reversed` exists on BenefitPayment; no service function or endpoint to perform the reversal + replacement flow atomically._

**US-PY09** `[GAP]`  
As **Fund Staff**, I want to run a monthly payment batch that creates and issues all recurring annuity payments, so that I don't have to create each payment manually.  
_Gap: No batch payment creation service function or endpoint. Each payment is created individually._

**US-PY10** `[GAP]`  
As **Fund Staff**, I want to generate and send a monthly check stub to each annuitant, so that they have a record of their gross amount, deductions, and net pay.  
_Gap: NetPayResult schema has all the data; no document template for a check stub letter._

---

## Tax Withholding (W-4P)

**US-TX01** `[BUILT]`  
As **Fund Staff**, I want to record a member's W-4P tax withholding election (filing status, Step 2 checkbox, claim amounts, additional withholding), so that federal withholding is calculated correctly.  
_Tests: test_net_pay_service.py, test_payment_service.py_

**US-TX02** `[BUILT]`  
As **Fund Staff**, I want to calculate the federal tax withholding for a payment using the IRS Pub 15-T percentage method, so that the correct amount is withheld.  
_Tests: test_net_pay_service.py_

**US-TX03** `[BUILT]`  
As **Fund Staff**, I want to calculate state income tax withholding (Illinois flat rate), so that state withholding is included in the net pay calculation.  
_Tests: test_net_pay_service.py_

**US-TX04** `[BUILT]`  
As **Fund Staff**, I want to update a member's withholding election by adding a new row (not editing the old one), so that the change history is preserved for audit.  
_Tests: test_payment_service.py_

**US-TX05** `[BUILT]`  
As **System Admin**, I want to seed the annual federal withholding tables (brackets, standard deduction amounts) at the start of each year, so that withholding calculations use current IRS rates.  
_Tests: test_net_pay_service.py — tests cover both 2025 and 2026 formats_

**US-TX06** `[GAP]`  
As **Fund Staff**, I want to support members who filed the pre-2020 W-4P (withholding allowances), so that their elections continue to be honored without requiring them to refile.  
_Gap: 2020+ redesign only. Pre-2020 allowance-based form is backlog item._

**US-TX07** `[GAP]`  
As **Fund Staff**, I want to generate a tax withholding notice for a member showing their current elections and expected annual withholding, so that they can verify their elections are correct.  
_Gap: No document template for tax withholding notice._

---

## Document Generation

**US-DG01** `[BUILT]`  
As **Fund Staff**, I want to generate a benefit estimate letter for a member with their projected annuity, so that they have a formal written estimate to take home.  
_Tests: test_document_service.py_

**US-DG02** `[BUILT]`  
As **Fund Staff**, I want to view the list of document templates available for generation, so that I know what letters and forms are available.  
_Tests: test_document_service.py_

**US-DG03** `[BUILT]`  
As **System Admin**, I want to register a new document template (slug, context providers, Jinja2 HTML file), so that a new letter type can be added without code changes.  
_Tests: test_document_service.py_

**US-DG04** `[BUILT]`  
As **Fund Staff**, I want to retrieve and download a previously generated document as a PDF, so that I can attach it to a physical file or re-send it.  
_Tests: test_document_service.py_

**US-DG05** `[GAP]`  
As **Fund Staff**, I want to generate a welcome letter for a new member, so that they receive introductory information about their pension plan.  
_Gap: Framework built; no welcome letter template created._

**US-DG06** `[GAP]`  
As **Fund Staff**, I want to generate an annual statement for each member showing their service credit, contributions, and projected benefit as of year-end, so that members have a yearly record.  
_Gap: Framework built; no annual statement template. Major planned document type._

**US-DG07** `[GAP]`  
As **Fund Staff**, I want to generate a 1099-R tax form for each annuitant showing their annual distributions, so that they can file their taxes correctly.  
_Gap: Framework built; no 1099-R template. Major planned document type._

**US-DG08** `[GAP]`  
As **Fund Staff**, I want to generate a retirement approval letter after a case is approved, so that the member receives formal written notice of their approved benefit amount.  
_Gap: Framework built; no retirement approval letter template._

**US-DG09** `[GAP]`  
As **Fund Staff**, I want to generate a deficiency billing notice to send to an employer with the invoice details, so that they receive a formal written bill.  
_Gap: Framework built; no billing notice template._

**US-DG10** `[STUB]`  
As **Fund Staff**, I want to send a digital form (e.g. W-4P update request) to a member and automatically ingest their response to update their elections, so that elections can be updated without manual data entry.  
_Gap: FormSubmission table stubbed; no parsing/ingest logic. Backlog item._

---

## Third-Party Entities

**US-TP01** `[BUILT]`  
As **Fund Staff**, I want to register a third-party payee (union dues, insurance carrier, court order) with their banking details, so that deduction payments can be disbursed to them.  
_Tests: (no dedicated test file; covered in net_pay_service tests)_

**US-TP02** `[BUILT]`  
As **Fund Staff**, I want to deactivate a third-party entity that is no longer accepting payments, so that it cannot be assigned to new deduction orders.  
_Tests: (no dedicated test file)_

**US-TP03** `[GAP]`  
As **Fund Staff**, I want to associate a court order with a garnishment deduction for a member, so that legal deductions are tracked as distinct from voluntary ones.  
_Gap: DeductionOrder supports court-order-type payees via ThirdPartyEntity FK; no court order workflow, case number tracking, or garnishment-specific lifecycle._

---

## API Keys & Access Control

**US-AK01** `[BUILT]`  
As **System Admin**, I want to create an API key with a name and defined scopes, so that an external integration can authenticate with the minimum permissions it needs.  
_Tests: test_api_key_service.py_

**US-AK02** `[BUILT]`  
As **System Admin**, I want to list all active API keys (without revealing the key values), so that I can audit what integrations have access.  
_Tests: test_api_key_service.py_

**US-AK03** `[BUILT]`  
As **System Admin**, I want to revoke an API key immediately, so that a compromised key cannot be used.  
_Tests: test_api_key_service.py_

**US-AK04** `[BUILT]`  
As **System Admin**, I want to rotate an API key (generating a new one and deactivating the old), so that keys can be cycled on a schedule or after a suspected compromise.  
_Tests: test_api_key_service.py_

**US-AK05** `[GAP]`  
As **System Admin**, I want to set an expiry date on an API key, so that integrations must periodically re-authenticate and I can enforce key rotation policy.  
_Gap: `expires_at` field exists on ApiKey model; not enforced at validation time in `deps.py`._

**US-AK06** `[GAP]`  
As **System Admin**, I want to see a log of the last time each API key was used and from which IP address, so that I can detect unusual access patterns.  
_Gap: `last_used_at` is updated; no IP address recorded; no access log or audit trail beyond the timestamp._

---

## System Configuration

**US-CF01** `[BUILT]`  
As **System Admin**, I want to seed fund-wide calculation configuration (multiplier, FAE window, normal ages, COLA type) via a script, so that the benefit engine uses fund-specific parameters.  
_Tests: test_fund_config_service.py, test_config_service.py_

**US-CF02** `[BUILT]`  
As **System Admin**, I want all fund rules to be effective-dated (new row supersedes old), so that historical calculations remain reproducible.  
_Tests: test_config_service.py_

**US-CF03** `[PARTIAL]`  
As **System Admin**, I want to view all current system configuration values via the admin UI, so that I can verify what rules are in effect.  
_Gap: System Config page exists in admin frontend but is read-only placeholder with no API backing._

**US-CF04** `[GAP]`  
As **System Admin**, I want to add or update a system configuration value via the admin UI with a future effective date, so that upcoming rule changes are staged without a DB migration.  
_Gap: System configurations are only writable via seed scripts. No admin UI write path._

**US-CF05** `[GAP]`  
As **System Admin**, I want to configure which employment types are valid for this fund, so that payroll submissions with unknown types are rejected.  
_Gap: `employment_types` config key is seeded; `contract_service.new_hire()` validates against it; but payroll ingestion does not validate employment type against the allowed list._

**US-CF06** `[GAP]`  
As **System Admin**, I want to configure which leave types are valid, so that invalid leave type codes are rejected at entry.  
_Gap: `leave_types` config key is seeded; `contract_service.begin_leave()` validates against it._

---

## Admin / LOB Frontend

**US-UI01** `[BUILT]`  
As **Fund Staff**, I want to view a dashboard summarizing key metrics (active members, pending cases, recent payroll submissions), so that I have a quick operational overview.  
_Gap: Dashboard page exists; content is placeholder/static — no live API data backing._

**US-UI02** `[BUILT]`  
As **Fund Staff**, I want to browse and search the member list, so that I can navigate to any member's detail page.  
_Gap: Member list page exists; no search/filter capability yet._

**US-UI03** `[BUILT]`  
As **Fund Staff**, I want to view a member's complete detail page (employment, salary, service credit, benefit estimate, retirement cases), so that I have all relevant information in one place.

**US-UI04** `[BUILT]`  
As **Fund Staff**, I want to view and manage employer records via the admin UI, so that I can maintain the employer directory.

**US-UI05** `[BUILT]`  
As **Fund Staff**, I want to view, upload, and review payroll reports via the admin UI, so that I can manage payroll submissions without using the raw API.

**US-UI06** `[BUILT]`  
As **Fund Staff**, I want to manage retirement cases (view, approve, activate, cancel) via the admin UI, so that I can process retirements through the UI.

**US-UI07** `[BUILT]`  
As **System Admin**, I want to create, view, and revoke API keys via the admin UI, so that I can manage integrations without a DB client.

**US-UI08** `[GAP]`  
As **Fund Staff**, I want a service purchase management page in the admin UI, so that I can create quotes, manage claims, and record payments without using the API directly.

**US-UI09** `[GAP]`  
As **Fund Staff**, I want a billing management page in the admin UI, so that I can view invoices, record payments, and generate deficiency bills without using the API directly.

**US-UI10** `[GAP]`  
As **Fund Staff**, I want a beneficiary and survivor management page in the admin UI, so that I can update beneficiaries, bank accounts, and benefit elections through the UI.

**US-UI11** `[GAP]`  
As **Fund Staff**, I want a payment disbursement page in the admin UI, so that I can view, create, and apply net pay to payments without using the API.

**US-UI12** `[GAP]`  
As **Fund Staff**, I want a document generation page in the admin UI, so that I can generate and download member letters without using the API.

**US-UI13** `[GAP]`  
As **System Admin**, I want a system configuration management page in the admin UI, so that I can view and update fund configuration without a DB client.

**US-UI14** `[GAP]`  
As **Fund Staff**, I want a third-party entities page in the admin UI, so that I can manage payees for deduction orders through the UI.

---

## Member Portal (Future)

**US-MP01** `[GAP]`  
As **Member**, I want to log in to a member portal and view my service credit balance, current salary on record, and projected benefit, so that I understand my retirement outlook.

**US-MP02** `[GAP]`  
As **Member**, I want to update my mailing address and contact information in the member portal, so that I don't have to call the fund office for simple changes.

**US-MP03** `[GAP]`  
As **Member**, I want to view and download my benefit estimate letter from the member portal, so that I have a record of my projected benefit.

**US-MP04** `[GAP]`  
As **Member**, I want to update my W-4P tax withholding elections in the member portal, so that my withholding is correct without having to mail in a paper form.

**US-MP05** `[GAP]`  
As **Member**, I want to view my annual statement in the member portal, so that I can verify my service credit and contribution totals each year.

**US-MP06** `[GAP]`  
As **Member**, I want to view and manage my beneficiary designations in the member portal, so that my survivor elections stay current.

**US-MP07** `[GAP]`  
As **Member**, I want to view the status of my service purchase claims and payment history in the member portal, so that I can track my purchase progress.

**US-MP08** `[GAP]`  
As **Annuitant (Member)**, I want to view my payment history and download check stubs in the member portal, so that I have records of my annuity payments.

---

## Reporting & Analytics (Future)

**US-RP01** `[GAP]`  
As **Fund Staff**, I want to run a contribution report for a date range showing total employer and employee contributions by employer, so that I can reconcile fund inflows.

**US-RP02** `[GAP]`  
As **Fund Staff**, I want to generate a delinquency report showing employers with outstanding invoices past their due date, so that I can prioritize collections.

**US-RP03** `[GAP]`  
As **Fund Staff**, I want to run a membership report showing active, terminated, and annuitant counts at a given date, so that actuarial assumptions can be validated.

**US-RP04** `[GAP]`  
As **Fund Staff**, I want to export a list of all annuitants with their monthly payment amounts, for actuarial review and financial planning.

**US-RP05** `[GAP]`  
As **System Admin**, I want to export a 1099-R batch file for all annuitants at year-end, so that tax forms can be generated and mailed.

---

## Summary

| Status | Count |
|---|---|
| `[BUILT]` | 60 |
| `[PARTIAL]` | 9 |
| `[STUB]` | 2 |
| `[GAP]` | 53 |
| **Total** | **124** |

### Highest-Priority Gaps (engine is built, gap is in surface area)

1. **Admin UI pages** — Billing, service purchase, beneficiaries, payments, documents, system config (US-UI08 through US-UI14)
2. **Annual statement + 1099-R templates** (US-DG06, US-DG07) — framework ready, templates missing
3. **Invoice overdue + interest accrual** (US-BL11, US-BL12) — model ready, no business logic
4. **Member address/contact CRUD** (US-M04, US-M05) — models exist, no API surface
5. **Payment batch + reversal workflows** (US-PY08, US-PY09) — model supports it, no service function
6. **Concurrent employment max credit enforcement** (US-E08) — config exists, not enforced
7. **System config admin UI write path** (US-CF04) — read-only placeholder only
8. **API key expiry enforcement** (US-AK05) — field exists, not checked

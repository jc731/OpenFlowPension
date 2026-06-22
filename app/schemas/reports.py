"""Pydantic schemas for report endpoints.

Every report returns a typed envelope:
  report_type   — machine name
  generated_at  — UTC timestamp of when the query ran
  parameters    — dict of inputs used (for UI display / audit)
  summary       — aggregated totals
  rows          — the data

The frontend ReportViewer component consumes this shape generically.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


# ── Contribution Reconciliation (RP01) ────────────────────────────────────────

class ContributionReconciliationRow(BaseModel):
    employer_id: uuid.UUID
    employer_name: str
    employer_code: str
    total_employee_contributions: Decimal
    total_employer_contributions: Decimal
    total_contributions: Decimal
    record_count: int


class ContributionReconciliationSummary(BaseModel):
    total_employee_contributions: Decimal
    total_employer_contributions: Decimal
    total_contributions: Decimal
    employer_count: int
    record_count: int


class ContributionReconciliationReport(BaseModel):
    report_type: str = "contribution_reconciliation"
    generated_at: datetime
    parameters: dict
    summary: ContributionReconciliationSummary
    rows: list[ContributionReconciliationRow]


# ── Delinquency (RP02) ────────────────────────────────────────────────────────

class DelinquencyRow(BaseModel):
    employer_id: uuid.UUID
    employer_name: str
    employer_code: str
    invoice_id: uuid.UUID
    invoice_type: str
    invoice_status: str
    due_date: date
    amount_due: Decimal
    amount_paid: Decimal
    outstanding: Decimal
    days_overdue: int


class DelinquencySummary(BaseModel):
    total_outstanding: Decimal
    invoice_count: int
    employer_count: int


class DelinquencyReport(BaseModel):
    report_type: str = "delinquency"
    generated_at: datetime
    parameters: dict
    summary: DelinquencySummary
    rows: list[DelinquencyRow]


# ── Membership Counts (RP03) ──────────────────────────────────────────────────

class MembershipCountRow(BaseModel):
    status: str
    count: int


class MembershipCountSummary(BaseModel):
    total_members: int
    note: str = "Reflects current member status, not a historical point-in-time snapshot."


class MembershipCountReport(BaseModel):
    report_type: str = "membership_counts"
    generated_at: datetime
    parameters: dict
    summary: MembershipCountSummary
    rows: list[MembershipCountRow]


# ── Annuitant Export (RP04) ───────────────────────────────────────────────────

class AnnuitantRow(BaseModel):
    member_id: uuid.UUID
    member_number: str
    first_name: str
    last_name: str
    member_status: str
    retirement_date: date | None
    benefit_option_type: str | None
    case_status: str | None
    final_monthly_annuity: Decimal | None
    first_payment_date: date | None
    payments_started: bool


class AnnuitantSummary(BaseModel):
    total_annuitants: int
    annuitants_with_approved_case: int
    total_monthly_outlay: Decimal
    note: str = (
        "Monthly outlay reflects approved/active retirement case amounts. "
        "Members listed without a case have annuitant status but no finalized benefit record."
    )


class AnnuitantReport(BaseModel):
    report_type: str = "annuitants"
    generated_at: datetime
    parameters: dict
    summary: AnnuitantSummary
    rows: list[AnnuitantRow]


# ── 1099-R (RP05) ─────────────────────────────────────────────────────────────

class Form1099RRecord(BaseModel):
    member_id: uuid.UUID
    member_number: str
    first_name: str
    last_name: str
    ssn_last_four: str
    # Box 1: gross distributions (all annuity payments issued in tax_year)
    gross_distributions: Decimal
    # Box 2a: taxable amount (gross minus any non-taxable exclusion — stub: same as gross)
    taxable_amount: Decimal
    # Box 4: federal income tax withheld
    federal_tax_withheld: Decimal
    # Box 14/16: state income tax withheld
    state_tax_withheld: Decimal
    # IRS distribution code (7 = normal distribution for annuity)
    distribution_code: str
    payer_name: str
    payer_ein: str | None


class Form1099RSummary(BaseModel):
    tax_year: int
    recipient_count: int
    total_gross_distributions: Decimal
    total_federal_withheld: Decimal
    total_state_withheld: Decimal


class Form1099RReport(BaseModel):
    report_type: str = "1099r"
    generated_at: datetime
    parameters: dict
    summary: Form1099RSummary
    rows: list[Form1099RRecord]

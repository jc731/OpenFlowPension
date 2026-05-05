from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


PayFrequency = Literal["monthly", "semi_monthly", "biweekly", "weekly"]
WithholdingType = Literal["formula", "flat_amount", "exempt"]


class NetPayDeductionInput(BaseModel):
    """A single pre-tax or post-tax deduction line for the stateless endpoint."""
    description: str
    deduction_type: str
    amount_type: Literal["fixed", "percent_of_gross"] = "fixed"
    amount: Decimal = Field(gt=0)
    is_pretax: bool = False
    # If set, this deduction is routed to the third-party disbursements tier instead
    third_party_entity_id: uuid.UUID | None = None


class ThirdPartyDisbursementInput(BaseModel):
    """A disbursement explicitly routed to a third-party entity.
    These appear after post-tax deductions in the check stub.
    Use this for child support, union dues, garnishments, insurance carriers, etc.
    """
    third_party_entity_id: uuid.UUID
    description: str
    deduction_type: str
    amount_type: Literal["fixed", "percent_of_gross"] = "fixed"
    amount: Decimal = Field(gt=0)


class NetPayTaxElectionInput(BaseModel):
    """Tax withholding parameters for the stateless endpoint.
    Maps directly to the fields on Form W-4P (2020+).
    """
    jurisdiction: str  # "federal" | "illinois"
    filing_status: Literal[
        "single",
        "married_filing_jointly",
        "married_filing_separately",
        "head_of_household",
        "qualifying_surviving_spouse",
    ]
    # formula  → full IRS Pub 15-T annualized percentage method (default)
    # flat_amount → withhold exactly additional_withholding each period, no formula
    # exempt   → zero withholding for this jurisdiction ("no state tax" option)
    withholding_type: WithholdingType = "formula"
    # W-4P Step 4(c): extra per-period amount added on top of formula result.
    # For withholding_type=flat_amount this IS the total flat amount withheld.
    additional_withholding: Decimal = Decimal("0")
    # W-4P Step 2: recipient has income from another job or pension.
    # When True, uses higher withholding rates (halved standard deduction).
    step_2_multiple_jobs: bool = False
    # W-4P Step 3: dependent tax credit amount (reduces computed tax dollar-for-dollar).
    step_3_dependent_credit: Decimal = Decimal("0")
    # W-4P Step 4(a): annual other income (added to annualized wages before brackets).
    step_4a_other_income: Decimal = Decimal("0")
    # W-4P Step 4(b): annual deductions beyond the standard deduction (reduces taxable income).
    step_4b_deductions: Decimal = Decimal("0")
    # Legacy field — prefer withholding_type="exempt" for new elections
    exempt: bool = False


class NetPayRequest(BaseModel):
    """Input for the stateless POST /calculate/net-pay endpoint."""
    gross_amount: Decimal = Field(gt=0)
    payment_date: date
    pay_frequency: PayFrequency = "monthly"
    deductions: list[NetPayDeductionInput] = []
    third_party_disbursements: list[ThirdPartyDisbursementInput] = []
    tax_elections: list[NetPayTaxElectionInput] = []


class NetPayLineItem(BaseModel):
    """One line on a check stub — a deduction, tax withholding, or third-party disbursement."""
    description: str
    amount: Decimal
    deduction_type: str
    is_pretax: bool
    deduction_order_id: uuid.UUID | None = None
    third_party_entity_id: uuid.UUID | None = None
    third_party_entity_name: str | None = None


class NetPayResult(BaseModel):
    """Full check-stub breakdown — everything needed to render or persist a payment.

    Math order:
        gross
        - pretax_deductions        → lowers taxable base
        = taxable_gross
        - tax_withholdings         → federal + state computed from W-4P
        - posttax_deductions       → internal deductions (no external payee)
        - third_party_disbursements → routed to external entities (courts, unions, etc.)
        = net_amount
    """
    gross_amount: Decimal
    pretax_deductions: list[NetPayLineItem]
    taxable_gross: Decimal
    tax_withholdings: list[NetPayLineItem]
    posttax_deductions: list[NetPayLineItem]
    third_party_disbursements: list[NetPayLineItem]
    net_amount: Decimal

    total_pretax_deductions: Decimal
    total_taxes: Decimal
    total_posttax_deductions: Decimal
    total_third_party_disbursements: Decimal
    total_deductions: Decimal

    payment_date: date
    tax_year: int
    pay_frequency: PayFrequency

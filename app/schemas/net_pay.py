from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


PayFrequency = Literal["monthly", "semi_monthly", "biweekly", "weekly"]


class NetPayDeductionInput(BaseModel):
    """A single deduction line for the stateless endpoint."""
    description: str
    deduction_type: str
    amount_type: Literal["fixed", "percent_of_gross"] = "fixed"
    amount: Decimal = Field(gt=0)
    is_pretax: bool = False
    third_party_entity_id: uuid.UUID | None = None


class NetPayTaxElectionInput(BaseModel):
    """Tax withholding parameters for the stateless endpoint."""
    jurisdiction: str  # "federal" | "illinois"
    filing_status: Literal[
        "single",
        "married_filing_jointly",
        "married_filing_separately",
        "head_of_household",
        "qualifying_surviving_spouse",
    ]
    additional_withholding: Decimal = Decimal("0")
    exempt: bool = False


class NetPayRequest(BaseModel):
    """Input for the stateless POST /calculate/net-pay endpoint."""
    gross_amount: Decimal = Field(gt=0)
    payment_date: date
    pay_frequency: PayFrequency = "monthly"
    deductions: list[NetPayDeductionInput] = []
    tax_elections: list[NetPayTaxElectionInput] = []


class NetPayLineItem(BaseModel):
    """One line on a check stub — a deduction or tax withholding."""
    description: str
    amount: Decimal
    deduction_type: str
    is_pretax: bool
    # Present when backed by a standing DeductionOrder
    deduction_order_id: uuid.UUID | None = None
    # Present when the payee is a third-party entity
    third_party_entity_id: uuid.UUID | None = None
    third_party_entity_name: str | None = None


class NetPayResult(BaseModel):
    """Full check-stub breakdown — everything needed to render or persist a payment."""
    gross_amount: Decimal
    pretax_deductions: list[NetPayLineItem]
    taxable_gross: Decimal
    tax_withholdings: list[NetPayLineItem]
    posttax_deductions: list[NetPayLineItem]
    net_amount: Decimal

    total_pretax_deductions: Decimal
    total_taxes: Decimal
    total_posttax_deductions: Decimal
    total_deductions: Decimal

    payment_date: date
    tax_year: int
    pay_frequency: PayFrequency

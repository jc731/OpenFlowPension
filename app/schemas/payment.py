from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ── Deduction order ────────────────────────────────────────────────────────────

class DeductionOrderCreate(BaseModel):
    deduction_type: str
    deduction_code: str | None = None
    amount_type: Literal["fixed", "percent_of_gross"] = "fixed"
    amount: Decimal = Field(gt=0)
    is_pretax: bool = False
    effective_date: date
    end_date: date | None = None
    source_document_type: Literal["court_order", "benefit_election", "union_authorization", "administrative"] | None = None
    source_document_id: str | None = None
    note: str | None = None


class DeductionOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    member_id: uuid.UUID
    deduction_type: str
    deduction_code: str | None
    amount_type: str
    amount: Decimal
    is_pretax: bool
    effective_date: date
    end_date: date | None
    source_document_type: str | None
    source_document_id: str | None
    note: str | None
    created_at: datetime


class DeductionOrderEnd(BaseModel):
    end_date: date


# ── Tax withholding election ───────────────────────────────────────────────────

class TaxWithholdingElectionCreate(BaseModel):
    jurisdiction: str  # "federal" | "illinois" | other
    filing_status: Literal[
        "single",
        "married_filing_jointly",
        "married_filing_separately",
        "head_of_household",
        "qualifying_surviving_spouse",
    ]
    additional_withholding: Decimal = Decimal("0")
    exempt: bool = False
    effective_date: date


class TaxWithholdingElectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    member_id: uuid.UUID
    jurisdiction: str
    filing_status: str
    additional_withholding: Decimal
    exempt: bool
    effective_date: date
    superseded_date: date | None
    created_at: datetime


# ── Payment deduction (per-payment applied deduction) ─────────────────────────

class PaymentDeductionCreate(BaseModel):
    deduction_type: str
    deduction_code: str | None = None
    amount: Decimal = Field(gt=0)
    is_pretax: bool = False
    deduction_order_id: uuid.UUID | None = None  # link to standing order if applicable
    note: str | None = None


class PaymentDeductionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    payment_id: uuid.UUID
    deduction_order_id: uuid.UUID | None
    deduction_type: str
    deduction_code: str | None
    amount: Decimal
    is_pretax: bool
    note: str | None
    created_at: datetime


# ── Benefit payment ───────────────────────────────────────────────────────────

class PaymentCreate(BaseModel):
    period_start: date
    period_end: date
    payment_date: date
    gross_amount: Decimal = Field(gt=0)
    payment_method: Literal["ach", "wire", "check", "eft", "other"]
    bank_account_id: uuid.UUID | None = None
    check_number: str | None = None
    apply_standing_orders: bool = True
    additional_deductions: list[PaymentDeductionCreate] = []
    note: str | None = None


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    member_id: uuid.UUID
    bank_account_id: uuid.UUID | None
    period_start: date
    period_end: date
    payment_date: date
    gross_amount: Decimal
    net_amount: Decimal
    status: str
    payment_method: str
    check_number: str | None
    issued_at: datetime | None
    note: str | None
    created_at: datetime
    deductions: list[PaymentDeductionRead] = []


class PaymentStatusUpdate(BaseModel):
    status: Literal["pending", "issued", "held", "reversed", "cancelled"]
    note: str | None = None

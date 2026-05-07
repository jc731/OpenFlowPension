from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class RateCreate(BaseModel):
    employer_id: uuid.UUID | None = None
    employment_type: str | None = None
    employee_rate: Decimal
    employer_rate: Decimal
    effective_date: date
    end_date: date | None = None
    note: str | None = None


class RateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    employer_id: uuid.UUID | None
    employment_type: str | None
    employee_rate: float
    employer_rate: float
    effective_date: date
    end_date: date | None
    note: str | None
    created_by: uuid.UUID | None


class DeficiencyCalcRequest(BaseModel):
    payroll_report_ids: list[uuid.UUID]


class DeficiencyCalcResult(BaseModel):
    total_deficiency: str
    employee_deficiency: str
    employer_deficiency: str
    row_count: int
    rows: list[dict[str, Any]]
    report_ids: list[str]


class DeficiencyInvoiceCreate(BaseModel):
    payroll_report_ids: list[uuid.UUID]
    due_date: date
    note: str | None = None


class SupplementalInvoiceCreate(BaseModel):
    amount_due: Decimal
    due_date: date
    line_items: list[dict[str, Any]]
    note: str | None = None


class VoidInvoiceRequest(BaseModel):
    void_reason: str


class InvoicePaymentCreate(BaseModel):
    amount: Decimal
    payment_date: date
    payment_method: str
    reference_number: str | None = None


class InvoicePaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    invoice_id: uuid.UUID
    amount: float
    payment_date: date
    payment_method: str
    reference_number: str | None
    received_by: uuid.UUID | None
    voided_at: datetime | None


class InvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    employer_id: uuid.UUID
    invoice_type: str
    status: str
    period_start: date | None
    period_end: date | None
    amount_due: float
    amount_paid: float
    interest_accrued: float
    due_date: date
    line_items: list[Any]
    source_report_ids: list[Any]
    note: str | None
    created_by: uuid.UUID | None
    issued_at: datetime | None
    paid_at: datetime | None
    voided_at: datetime | None
    voided_by: uuid.UUID | None
    void_reason: str | None
    payments: list[InvoicePaymentRead] = []

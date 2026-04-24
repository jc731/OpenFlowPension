from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# ── Input ─────────────────────────────────────────────────────────────────────

class PayrollRowInput(BaseModel):
    member_number: str
    period_start: date
    period_end: date
    gross_earnings: Decimal = Field(ge=0)
    employee_contribution: Decimal = Field(ge=0)
    employer_contribution: Decimal = Field(ge=0)
    days_worked: int = Field(ge=0)


class PayrollReportCreate(BaseModel):
    note: str | None = None
    rows: list[PayrollRowInput]


# ── Read ──────────────────────────────────────────────────────────────────────

class ContributionRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    member_id: uuid.UUID
    employment_id: uuid.UUID | None
    payroll_report_row_id: uuid.UUID | None
    period_start: date
    period_end: date
    employee_contribution: Decimal
    employer_contribution: Decimal
    contribution_type: str
    voided_at: datetime | None
    void_reason: str | None
    created_at: datetime


class PayrollReportRowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    payroll_report_id: uuid.UUID
    member_number: str
    member_id: uuid.UUID | None
    employment_id: uuid.UUID | None
    period_start: date
    period_end: date
    gross_earnings: Decimal
    employee_contribution: Decimal
    employer_contribution: Decimal
    days_worked: int
    status: str
    error_message: str | None
    created_at: datetime


class PayrollReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employer_id: uuid.UUID
    source_format: str
    source_filename: str | None
    status: str
    row_count: int
    processed_count: int
    error_count: int
    skipped_count: int
    submitted_by: uuid.UUID | None
    note: str | None
    created_at: datetime
    rows: list[PayrollReportRowRead] = []

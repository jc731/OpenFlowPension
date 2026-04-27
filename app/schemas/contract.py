from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# ── New hire ──────────────────────────────────────────────────────────────────

class NewHireCreate(BaseModel):
    employer_id: uuid.UUID
    employment_type: str
    position_title: str | None = None
    department: str | None = None
    hire_date: date
    percent_time: float = Field(default=100.0, gt=0, le=100)
    is_primary: bool = True
    annual_salary: Decimal = Field(gt=0)
    salary_type: str = "annual"
    note: str | None = None


# ── Termination ───────────────────────────────────────────────────────────────

class TerminationCreate(BaseModel):
    termination_date: date
    termination_reason: str | None = None
    note: str | None = None


# ── Leave of absence ──────────────────────────────────────────────────────────

class LeaveBeginCreate(BaseModel):
    leave_type: str
    start_date: date
    expected_return_date: date | None = None
    is_paid: bool = False
    note: str | None = None


class LeaveEndCreate(BaseModel):
    actual_return_date: date
    note: str | None = None


# ── Percent-time change ───────────────────────────────────────────────────────

class PercentTimeChangeCreate(BaseModel):
    new_percent_time: float = Field(gt=0, le=100)
    effective_date: date
    new_annual_salary: Decimal | None = Field(default=None, gt=0)
    change_reason: str | None = None
    note: str | None = None


# ── Status transitions (explicit admin actions) ───────────────────────────────

class DeathRecordCreate(BaseModel):
    death_date: date
    note: str | None = None


class BeginAnnuityCreate(BaseModel):
    effective_date: date
    note: str | None = None


class RefundStatusCreate(BaseModel):
    effective_date: date
    note: str | None = None


# ── Read schemas ──────────────────────────────────────────────────────────────

class MemberStatusHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    member_id: uuid.UUID
    status: str
    effective_date: date
    reason: str | None
    source_event: str | None
    source_record_id: uuid.UUID | None
    changed_by: uuid.UUID | None
    note: str | None
    created_at: datetime


class LeavePeriodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employment_id: uuid.UUID
    leave_type: str
    start_date: date
    expected_return_date: date | None
    actual_return_date: date | None
    is_paid: bool
    note: str | None
    created_at: datetime

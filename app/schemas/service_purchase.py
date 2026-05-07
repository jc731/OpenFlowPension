import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


# ── Quote ──────────────────────────────────────────────────────────────────────

class ServicePurchaseQuoteRequest(BaseModel):
    purchase_type: str
    credit_years: Decimal
    period_start: date
    period_end: date


class ServicePurchaseQuoteResult(BaseModel):
    purchase_type: str
    credit_entry_type: str
    credit_years: Decimal
    cost_total: Decimal
    cost_breakdown: dict
    installment_allowed: bool
    credit_grant_on: str


# ── Claim CRUD ─────────────────────────────────────────────────────────────────

class ServicePurchaseClaimCreate(BaseModel):
    purchase_type: str
    credit_years: Decimal
    period_start: date
    period_end: date
    notes: str | None = None
    params: dict = {}


class ServicePurchaseClaimRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    member_id: uuid.UUID
    purchase_type: str
    status: str
    credit_entry_type: str
    credit_years: Decimal
    period_start: date
    period_end: date
    cost_total: Decimal
    cost_paid: Decimal
    cost_breakdown: dict
    installment_allowed: bool
    credit_grant_on: str
    approved_at: datetime | None
    approved_by: uuid.UUID | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    params: dict
    notes: str | None
    created_at: datetime
    payments: list["ServicePurchasePaymentRead"] = []


# ── Approve / Cancel ───────────────────────────────────────────────────────────

class ApprovePurchaseClaimRequest(BaseModel):
    notes: str | None = None


class CancelPurchaseClaimRequest(BaseModel):
    cancel_reason: str


# ── Payment ────────────────────────────────────────────────────────────────────

class ServicePurchasePaymentCreate(BaseModel):
    amount: Decimal
    payment_date: date
    payment_method: str
    reference_number: str | None = None


class ServicePurchasePaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    claim_id: uuid.UUID
    amount: Decimal
    payment_date: date
    payment_method: str
    reference_number: str | None
    received_by: uuid.UUID | None
    voided_at: datetime | None
    created_at: datetime


ServicePurchaseClaimRead.model_rebuild()

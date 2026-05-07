from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.member import Member


class ServicePurchaseClaim(Base):
    """Tracks a service purchase from quote through payment to credit grant.

    Lifecycle: draft → pending_approval → approved → in_payment → completed
               (any non-completed state) → cancelled
    """

    __tablename__ = "service_purchase_claims"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"), nullable=False)

    # Purchase type key — matches a key in service_purchase_types system config
    purchase_type: Mapped[str] = mapped_column(String, nullable=False)

    # draft | pending_approval | approved | in_payment | completed | cancelled
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft", server_default="draft")

    # ServiceCreditEntry.entry_type that will be written on credit grant
    credit_entry_type: Mapped[str] = mapped_column(String, nullable=False)

    # Credit to be granted (in years)
    credit_years: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)

    # Period being purchased
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    # Cost snapshot at claim creation
    cost_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    cost_paid: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    cost_breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    # Copied from type config at creation — immutable thereafter
    installment_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # approval | first_payment | completion
    credit_grant_on: Mapped[str] = mapped_column(String, nullable=False, default="completion")

    # Audit trail
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Type-specific extras: DD-214 reference number, prior system name, etc.
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    member: Mapped[Member] = relationship()
    payments: Mapped[list[ServicePurchasePayment]] = relationship(back_populates="claim")


class ServicePurchasePayment(Base):
    """Append-only payment ledger for a service purchase claim.

    Void pattern: set voided_at/voided_by/void_reason — never delete.
    """

    __tablename__ = "service_purchase_payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("service_purchase_claims.id"), nullable=False
    )

    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)

    # check | ach | payroll_deduction | wire
    payment_method: Mapped[str] = mapped_column(String, nullable=False)
    reference_number: Mapped[str | None] = mapped_column(String, nullable=True)

    received_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    claim: Mapped[ServicePurchaseClaim] = relationship(back_populates="payments")

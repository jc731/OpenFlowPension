from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.employer import Employer


class EmployerContributionRate(TimestampMixin, Base):
    """Authoritative contribution rates with specificity-based fallback.

    Lookup priority (most specific wins):
      employer_id + employment_type  → employer-specific type override
      employer_id only               → employer-wide override (all types)
      employment_type only           → fund-wide type default (e.g. police/fire)
      neither                        → fund-wide catch-all default
    """

    __tablename__ = "employer_contribution_rates"

    # null = applies to all employers; set for employer-specific exceptions
    employer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employers.id"), nullable=True
    )
    # null = applies to all employment types
    employment_type: Mapped[str | None] = mapped_column(String, nullable=True)

    employee_rate: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    employer_rate: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)

    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class EmployerInvoice(Base):
    """Billing record for deficiency or supplemental charges.

    Lifecycle: draft → issued → paid (or voided from any non-paid state)
    amount_paid is denormalized from sum of non-voided EmployerInvoicePayment rows.
    """

    __tablename__ = "employer_invoices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    employer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employers.id"), nullable=False
    )

    # deficiency | supplemental
    invoice_type: Mapped[str] = mapped_column(String, nullable=False)

    # draft | issued | paid | overdue | voided
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft", server_default="draft")

    # Period covered — set for deficiency, null for supplemental
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)

    amount_due: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    amount_paid: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    interest_accrued: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0, server_default="0")

    due_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Detailed breakdown: employee_deficiency, employer_deficiency, interest, ual_assessment, etc.
    line_items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")

    # PayrollReport IDs that sourced this invoice — for future accounting linkage
    source_report_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    employer: Mapped[Employer] = relationship()
    payments: Mapped[list[EmployerInvoicePayment]] = relationship(back_populates="invoice")


class EmployerInvoicePayment(Base):
    """Append-only payment ledger for employer invoices. Void pattern — never delete."""

    __tablename__ = "employer_invoice_payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employer_invoices.id"), nullable=False
    )

    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_method: Mapped[str] = mapped_column(String, nullable=False)
    reference_number: Mapped[str | None] = mapped_column(String, nullable=True)
    received_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    invoice: Mapped[EmployerInvoice] = relationship(back_populates="payments")

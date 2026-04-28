from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.bank_account import MemberBankAccount
    from app.models.beneficiary import Beneficiary, BeneficiaryBankAccount
    from app.models.member import Member


class BenefitPayment(Base):
    """One row per member per pay period. Amounts are immutable once status=issued."""

    __tablename__ = "benefit_payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"), nullable=False)
    bank_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("member_bank_accounts.id"), nullable=True
    )
    # Set on survivor_annuity / death_benefit payments; null on annuity/refund payments
    beneficiary_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("beneficiaries.id"), nullable=True
    )
    beneficiary_bank_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("beneficiary_bank_accounts.id"), nullable=True
    )

    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)

    gross_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    net_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    # annuity | refund | death_benefit | survivor_annuity | lump_sum | other
    payment_type: Mapped[str] = mapped_column(String, nullable=False, default="annuity", server_default="annuity")
    # pending | issued | held | reversed | cancelled
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", server_default="pending")
    # ach | wire | check | eft | other
    payment_method: Mapped[str] = mapped_column(String, nullable=False)

    check_number: Mapped[str | None] = mapped_column(String, nullable=True)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    member: Mapped[Member] = relationship(back_populates="payments")
    bank_account: Mapped[MemberBankAccount | None] = relationship(back_populates="payments")
    beneficiary: Mapped[Beneficiary | None] = relationship(foreign_keys=[beneficiary_id])
    beneficiary_bank_account: Mapped[BeneficiaryBankAccount | None] = relationship(
        foreign_keys=[beneficiary_bank_account_id]
    )
    deductions: Mapped[list[PaymentDeduction]] = relationship(back_populates="payment")


class PaymentDeduction(Base):
    """Append-only ledger of deductions applied to a payment. Never UPDATE or DELETE rows."""

    __tablename__ = "payment_deductions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("benefit_payments.id"), nullable=False
    )
    deduction_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deduction_orders.id"), nullable=True
    )

    # Well-known types: federal_tax | state_tax | medicare | health_insurance |
    # dental | vision | life_insurance | union_dues | child_support | garnishment | other
    deduction_type: Mapped[str] = mapped_column(String, nullable=False)
    deduction_code: Mapped[str | None] = mapped_column(String, nullable=True)

    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    is_pretax: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    payment: Mapped[BenefitPayment] = relationship(back_populates="deductions")
    order: Mapped[DeductionOrder | None] = relationship(back_populates="payment_deductions")


class DeductionOrder(Base):
    """Standing deduction authorization. One row per member per recurring deduction."""

    __tablename__ = "deduction_orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"), nullable=False)

    deduction_type: Mapped[str] = mapped_column(String, nullable=False)
    deduction_code: Mapped[str | None] = mapped_column(String, nullable=True)

    # fixed | percent_of_gross
    amount_type: Mapped[str] = mapped_column(String, nullable=False, default="fixed", server_default="fixed")
    amount: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)

    is_pretax: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # court_order | benefit_election | union_authorization | administrative
    source_document_type: Mapped[str | None] = mapped_column(String, nullable=True)
    source_document_id: Mapped[str | None] = mapped_column(String, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    member: Mapped[Member] = relationship(back_populates="deduction_orders")
    payment_deductions: Mapped[list[PaymentDeduction]] = relationship(back_populates="order")


class TaxWithholdingElection(Base):
    """Member W-4 / state withholding election. Immutable — new row supersedes old."""

    __tablename__ = "tax_withholding_elections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"), nullable=False)

    # federal | illinois | (extensible string for other jurisdictions)
    jurisdiction: Mapped[str] = mapped_column(String, nullable=False)
    # single | married_filing_jointly | married_filing_separately |
    # head_of_household | qualifying_surviving_spouse
    filing_status: Mapped[str] = mapped_column(String, nullable=False)
    additional_withholding: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0, server_default="0")
    exempt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    superseded_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    member: Mapped[Member] = relationship(back_populates="tax_withholding_elections")

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, LargeBinary, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.address import MemberAddress
    from app.models.bank_account import MemberBankAccount
    from app.models.beneficiary import Beneficiary
    from app.models.contact import MemberContact
    from app.models.employment import EmploymentRecord
    from app.models.member_status import MemberStatusHistory
    from app.models.payment import BenefitPayment, DeductionOrder, TaxWithholdingElection
    from app.models.plan_config import PlanTier, PlanType
    from app.models.service_credit import ServiceCreditEntry


class Member(TimestampMixin, Base):
    __tablename__ = "members"

    member_number: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    middle_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    suffix: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    ssn_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    ssn_last_four: Mapped[str] = mapped_column(String(4), nullable=False)
    gender: Mapped[str | None] = mapped_column(String, nullable=True)

    member_status: Mapped[str] = mapped_column(String, nullable=False, default="active", server_default="active")
    status_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    plan_tier_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("plan_tiers.id"), nullable=True)
    plan_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("plan_types.id"), nullable=True)
    plan_choice_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    plan_choice_locked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    certification_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    certification_date_source: Mapped[str] = mapped_column(String, default="calculated", server_default="calculated")
    certification_date_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    certification_date_set_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    certification_date_set_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    plan_tier: Mapped[PlanTier | None] = relationship("PlanTier", foreign_keys=[plan_tier_id])
    plan_type: Mapped[PlanType | None] = relationship("PlanType", foreign_keys=[plan_type_id])
    addresses: Mapped[list[MemberAddress]] = relationship(back_populates="member")
    contacts: Mapped[list[MemberContact]] = relationship(back_populates="member")
    beneficiaries: Mapped[list[Beneficiary]] = relationship(back_populates="member")
    employment_records: Mapped[list[EmploymentRecord]] = relationship(back_populates="member")
    service_credit_entries: Mapped[list[ServiceCreditEntry]] = relationship(back_populates="member")
    bank_accounts: Mapped[list[MemberBankAccount]] = relationship(back_populates="member")
    payments: Mapped[list[BenefitPayment]] = relationship(back_populates="member")
    deduction_orders: Mapped[list[DeductionOrder]] = relationship(back_populates="member")
    tax_withholding_elections: Mapped[list[TaxWithholdingElection]] = relationship(back_populates="member")
    status_history: Mapped[list[MemberStatusHistory]] = relationship(back_populates="member", order_by="MemberStatusHistory.effective_date")

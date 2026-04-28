from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.beneficiary import Beneficiary
    from app.models.member import Member
    from app.models.payment import BenefitPayment


class RetirementCase(TimestampMixin, Base):
    """Administrative workflow record for processing a member's retirement.

    Status flow:
      draft     → approved → active
      draft     → cancelled
      approved  → cancelled

    The calculation_snapshot JSONB field stores the full BenefitCalculationResult
    serialized at the time of the last calculate/recalculate call. It is the
    permanent record of what was reviewed and approved.

    Invariants:
      - Only one non-cancelled case per member (enforced by service layer).
      - Amounts are immutable once status=approved.
      - final_monthly_annuity is denormalized from the snapshot for fast reads.
    """

    __tablename__ = "retirement_cases"

    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), nullable=False
    )

    # draft | approved | active | cancelled
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft", server_default="draft")

    retirement_date: Mapped[date] = mapped_column(Date, nullable=False)
    termination_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sick_leave_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # Benefit option inputs — passed through to BenefitCalculationRequest
    benefit_option_type: Mapped[str] = mapped_column(
        String, nullable=False, default="single_life", server_default="single_life"
    )
    beneficiary_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("beneficiaries.id"), nullable=True
    )
    beneficiary_age_at_retirement: Mapped[int | None] = mapped_column(Integer, nullable=True)
    desired_reversionary_monthly: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    # Full BenefitCalculationResult stored as JSONB (serialized via model_dump(mode='json'))
    calculation_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Denormalized from snapshot — set at approval, immutable thereafter
    final_monthly_annuity: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    # First payment created at activation
    first_payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    first_payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("benefit_payments.id"), nullable=True
    )

    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    member: Mapped[Member] = relationship(foreign_keys=[member_id])
    beneficiary: Mapped[Beneficiary | None] = relationship(foreign_keys=[beneficiary_id])
    first_payment: Mapped[BenefitPayment | None] = relationship(foreign_keys=[first_payment_id])

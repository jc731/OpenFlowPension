from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.beneficiary import Beneficiary
    from app.models.member import Member


class MemberBenefitElection(Base):
    """Elected benefit option recorded at (or before) retirement.

    Drives survivor benefit calculation after the member's death:
      single_life   → no survivor benefit
      js_50/75/100  → survivor receives that % of member_monthly_annuity
      reversionary  → survivor receives reversionary_monthly_amount

    One active election per member. Replace by inserting a new row with a
    later effective_date; the survivor service always uses the most recent.
    """

    __tablename__ = "member_benefit_elections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), nullable=False
    )

    # single_life | reversionary | js_50 | js_75 | js_100
    option_type: Mapped[str] = mapped_column(String, nullable=False)

    # Designated survivor (null for single_life)
    beneficiary_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("beneficiaries.id"), nullable=True
    )
    # Age of beneficiary at time of election — locked in for actuarial record
    beneficiary_age_at_election: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Member's annuity AFTER option reduction (what they actually receive monthly)
    member_monthly_annuity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Only set for reversionary option: the elected monthly amount to the survivor
    reversionary_monthly_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    elected_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    member: Mapped[Member] = relationship(back_populates="benefit_elections")
    beneficiary: Mapped[Beneficiary | None] = relationship(foreign_keys=[beneficiary_id])

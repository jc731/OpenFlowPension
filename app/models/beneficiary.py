from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, LargeBinary, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship as orm_relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.member import Member


class Beneficiary(TimestampMixin, Base):
    """Beneficiary designation on a member account.

    beneficiary_type controls which name fields are used:
      individual   → first_name + last_name (+ optional ssn)
      estate       → org_name (e.g. "Estate of Jane Smith")
      trust        → org_name
      organization → org_name

    linked_member_id: if the beneficiary is also a pension system member,
    link here so demographic data can be sourced from their Member record.
    This is the bridge field for the future party model refactor — see CLAUDE.md.
    """

    __tablename__ = "beneficiaries"

    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"), nullable=False)

    # individual | estate | trust | organization
    beneficiary_type: Mapped[str] = mapped_column(
        String, nullable=False, default="individual", server_default="individual"
    )

    # Used when beneficiary_type = individual
    first_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    ssn_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    ssn_last_four: Mapped[str | None] = mapped_column(String(4), nullable=True)

    # Used when beneficiary_type = estate | trust | organization
    org_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    # If this beneficiary is also a pension system member, link their record.
    # When set, current demographic data comes from the Member record.
    # Bridge field for the future party model refactor — see CLAUDE.md.
    linked_member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), nullable=True
    )

    relationship: Mapped[str] = mapped_column(String, nullable=False)
    share_percent: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    member: Mapped[Member] = orm_relationship(back_populates="beneficiaries", foreign_keys="[Beneficiary.member_id]")
    linked_member: Mapped[Member | None] = orm_relationship(foreign_keys="[Beneficiary.linked_member_id]")
    bank_accounts: Mapped[list[BeneficiaryBankAccount]] = orm_relationship(back_populates="beneficiary")


class BeneficiaryBankAccount(Base):
    """Bank account for a beneficiary — used for survivor/death benefit payments.

    Same Fernet encryption pattern as MemberBankAccount. Never returned in API
    responses; account_last_four used for display. Never update routing/account
    fields — add a new row and close the old one.
    """

    __tablename__ = "beneficiary_bank_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    beneficiary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("beneficiaries.id"), nullable=False
    )

    bank_name: Mapped[str] = mapped_column(Text, nullable=False)
    routing_number: Mapped[str] = mapped_column(String(9), nullable=False)
    account_number_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    account_last_four: Mapped[str] = mapped_column(String(4), nullable=False)
    account_type: Mapped[str] = mapped_column(String, nullable=False)  # checking | savings

    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    beneficiary: Mapped[Beneficiary] = orm_relationship(back_populates="bank_accounts")

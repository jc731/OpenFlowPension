from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, LargeBinary, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.member import Member
    from app.models.payment import BenefitPayment


class MemberBankAccount(Base):
    __tablename__ = "member_bank_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"), nullable=False)

    bank_name: Mapped[str] = mapped_column(String, nullable=False)
    routing_number: Mapped[str] = mapped_column(String(9), nullable=False)
    account_number_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    account_last_four: Mapped[str] = mapped_column(String(4), nullable=False)
    account_type: Mapped[str] = mapped_column(String, nullable=False)  # checking | savings

    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    member: Mapped[Member] = relationship(back_populates="bank_accounts")
    payments: Mapped[list[BenefitPayment]] = relationship(back_populates="bank_account")

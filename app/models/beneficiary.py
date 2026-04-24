from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, LargeBinary, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import relationship as orm_relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.member import Member


class Beneficiary(TimestampMixin, Base):
    __tablename__ = "beneficiaries"

    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"), nullable=False)
    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    relationship: Mapped[str] = mapped_column(String, nullable=False)
    beneficiary_type: Mapped[str] = mapped_column(String, nullable=False)
    share_percent: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    ssn_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    ssn_last_four: Mapped[str | None] = mapped_column(String(4), nullable=True)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    member: Mapped[Member] = orm_relationship(back_populates="beneficiaries")

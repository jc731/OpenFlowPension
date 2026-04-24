from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.employment import EmploymentRecord


class LeaveType(TimestampMixin, Base):
    __tablename__ = "leave_types"

    type_code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    type_label: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rules: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    leave_balances: Mapped[list[LeaveBalance]] = relationship(back_populates="leave_type")


class LeaveBalance(Base):
    __tablename__ = "leave_balances"
    __table_args__ = (
        UniqueConstraint("employment_id", "leave_type_id", "balance_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )

    employment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employment_records.id"), nullable=False)
    leave_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("leave_types.id"), nullable=False)
    balance_date: Mapped[date] = mapped_column(Date, nullable=False)
    balance_hours: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    employment: Mapped[EmploymentRecord] = relationship(back_populates="leave_balances")
    leave_type: Mapped[LeaveType] = relationship(back_populates="leave_balances")

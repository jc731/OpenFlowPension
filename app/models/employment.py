from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.employer import Employer
    from app.models.leave import LeaveBalance
    from app.models.member import Member
    from app.models.plan_config import PlanTier, PlanType
    from app.models.salary import SalaryHistory
    from app.models.service_credit import ServiceCreditEntry


class EmploymentRecord(TimestampMixin, Base):
    __tablename__ = "employment_records"

    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"), nullable=False)
    employer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employers.id"), nullable=False)
    employment_type: Mapped[str] = mapped_column(String, nullable=False)
    position_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    hire_date: Mapped[date] = mapped_column(Date, nullable=False)
    termination_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    termination_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    percent_time: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=100.00, server_default="100.00")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    concurrent_employment_group: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    member: Mapped[Member] = relationship(back_populates="employment_records")
    employer: Mapped[Employer] = relationship(back_populates="employment_records")
    salary_history: Mapped[list[SalaryHistory]] = relationship(back_populates="employment")
    leave_balances: Mapped[list[LeaveBalance]] = relationship(back_populates="employment")
    service_credit_entries: Mapped[list[ServiceCreditEntry]] = relationship(back_populates="employment")

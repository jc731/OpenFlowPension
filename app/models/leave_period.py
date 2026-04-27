from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.employment import EmploymentRecord


class LeavePeriod(Base):
    """Tracks a discrete leave-of-absence period for an employment record.

    Separate from LeaveBalance (which tracks accrual hours). LeavePeriod is
    the audit trail for LOA history — paid vs unpaid matters for service credit.
    """

    __tablename__ = "leave_periods"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    employment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employment_records.id"), nullable=False
    )

    # medical | personal | military | family | other — validated against system_configurations
    leave_type: Mapped[str] = mapped_column(String, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_return_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_return_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    is_paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    employment: Mapped[EmploymentRecord] = relationship(back_populates="leave_periods")

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.employment import EmploymentRecord


class SalaryHistory(Base):
    __tablename__ = "salary_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )

    employment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employment_records.id"), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    annual_salary: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    salary_type: Mapped[str] = mapped_column(String, default="annual", server_default="annual")
    hourly_rate: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    employment: Mapped[EmploymentRecord] = relationship(back_populates="salary_history")

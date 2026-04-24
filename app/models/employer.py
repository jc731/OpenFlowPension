from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.employment import EmploymentRecord
    from app.models.payroll import PayrollReport


class Employer(TimestampMixin, Base):
    __tablename__ = "employers"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    employer_code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    employer_type: Mapped[str] = mapped_column(String, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    employment_records: Mapped[list[EmploymentRecord]] = relationship(back_populates="employer")
    payroll_reports: Mapped[list[PayrollReport]] = relationship(back_populates="employer")

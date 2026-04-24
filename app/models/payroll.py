from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.employer import Employer
    from app.models.employment import EmploymentRecord
    from app.models.member import Member


class PayrollReport(Base):
    """Batch submission header — one per employer per upload."""

    __tablename__ = "payroll_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    employer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employers.id"), nullable=False)

    # csv | json | manual
    source_format: Mapped[str] = mapped_column(String, nullable=False)
    source_filename: Mapped[str | None] = mapped_column(String, nullable=True)

    # pending | processing | completed | failed
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", server_default="pending")

    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    submitted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    employer: Mapped[Employer] = relationship(back_populates="payroll_reports")
    rows: Mapped[list[PayrollReportRow]] = relationship(back_populates="report")


class PayrollReportRow(Base):
    """One member record within a payroll report batch."""

    __tablename__ = "payroll_report_rows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    payroll_report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payroll_reports.id"), nullable=False
    )

    # Raw lookup key from the file; member_id resolved after validation
    member_number: Mapped[str] = mapped_column(String, nullable=False)
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), nullable=True
    )
    employment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employment_records.id"), nullable=True
    )

    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    gross_earnings: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    employee_contribution: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    employer_contribution: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    days_worked: Mapped[int] = mapped_column(Integer, nullable=False)

    # pending | applied | error | skipped
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", server_default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Original row preserved verbatim for audit
    raw_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    report: Mapped[PayrollReport] = relationship(back_populates="rows")
    member: Mapped[Member | None] = relationship()
    employment: Mapped[EmploymentRecord | None] = relationship()
    contribution_records: Mapped[list[ContributionRecord]] = relationship(back_populates="payroll_row")


class ContributionRecord(Base):
    """Append-only ledger of employee + employer contributions. Feeds Money Purchase C&I."""

    __tablename__ = "contribution_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"), nullable=False)
    employment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employment_records.id"), nullable=True
    )
    payroll_report_row_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payroll_report_rows.id"), nullable=True
    )

    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    employee_contribution: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    employer_contribution: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    # normal | ope | military — drives MP formula multiplier
    contribution_type: Mapped[str] = mapped_column(
        String, nullable=False, default="normal", server_default="normal"
    )

    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    member: Mapped[Member] = relationship()
    payroll_row: Mapped[PayrollReportRow | None] = relationship(back_populates="contribution_records")

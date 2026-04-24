from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, event, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.employment import EmploymentRecord
    from app.models.member import Member
    from app.models.plan_config import SystemConfiguration


class ServiceCreditEntry(Base):
    __tablename__ = "service_credit_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"), nullable=False)
    employment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employment_records.id"), nullable=True)
    entry_type: Mapped[str] = mapped_column(String, nullable=False)
    credit_days: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    credit_years: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    accrual_rule_config_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("system_configurations.id"), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    member: Mapped[Member] = relationship(back_populates="service_credit_entries")
    employment: Mapped[EmploymentRecord | None] = relationship(back_populates="service_credit_entries")
    accrual_rule_config: Mapped[SystemConfiguration | None] = relationship("SystemConfiguration")


@event.listens_for(ServiceCreditEntry, "before_update")
def prevent_service_credit_update(mapper, connection, target):
    raise RuntimeError(
        "service_credit_entries is an append-only ledger. "
        "To correct an entry: void the original (set voided_at/void_reason) and insert a new entry."
    )

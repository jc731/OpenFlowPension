from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.member import Member


class MemberStatusHistory(Base):
    """Append-only log of member lifecycle status transitions.

    Status is stored explicitly (not recomputed on every read) because
    'inactive' (refund taken) requires knowing balance history, which is
    expensive to derive. Every contract event writes a new row here.

    Valid statuses: active | on_leave | terminated | inactive | annuitant | deceased
    """

    __tablename__ = "member_status_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"), nullable=False)

    # active | on_leave | terminated | inactive | annuitant | deceased
    status: Mapped[str] = mapped_column(String, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Why the status changed (e.g. "voluntary_resignation", "retirement", "death")
    reason: Mapped[str | None] = mapped_column(String, nullable=True)

    # Which contract event triggered this row
    source_event: Mapped[str | None] = mapped_column(String, nullable=True)

    # UUID of the record that triggered the transition (employment_record, leave_period, etc.)
    source_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    member: Mapped[Member] = relationship(back_populates="status_history")

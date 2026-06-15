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


class MemberNameHistory(Base):
    """Append-only log of member legal name changes.

    Written before every update to first_name / last_name on Member. The row
    captures the name that is being replaced, not the new name, so the full
    chain is reconstructable: read rows in effective_date order → final current
    name is on the Member row itself.

    Rows are never updated or deleted.
    """

    __tablename__ = "member_name_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"), nullable=False)

    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    middle_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    suffix: Mapped[str | None] = mapped_column(Text, nullable=True)

    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    member: Mapped[Member] = relationship(back_populates="name_history")

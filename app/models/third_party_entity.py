from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ThirdPartyEntity(Base):
    """Payee organizations for disbursement routing — unions, courts, insurers, etc."""

    __tablename__ = "third_party_entities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()")
    )

    name: Mapped[str] = mapped_column(String, nullable=False)
    # disbursement_unit | union | insurance_carrier | court | other
    entity_type: Mapped[str] = mapped_column(String, nullable=False, default="other", server_default="other")

    address_line1: Mapped[str | None] = mapped_column(String, nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String, nullable=True)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)

    ein: Mapped[str | None] = mapped_column(String, nullable=True)

    # ACH / payment routing — account number encrypted at app layer
    bank_routing_number: Mapped[str | None] = mapped_column(String(9), nullable=True)
    bank_account_number_encrypted: Mapped[bytes | None] = mapped_column(nullable=True)
    bank_account_last_four: Mapped[str | None] = mapped_column(String(4), nullable=True)
    # ach | check | wire | other
    payment_method: Mapped[str | None] = mapped_column(String, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

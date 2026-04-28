from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ApiKey(Base):
    """Machine-to-machine API key.

    Key lifecycle:
      - Create: generate random plaintext key, return once, store only SHA-256 hash.
      - Validate: hash the incoming Bearer token, look up by key_hash.
      - Revoke: set active=False (never delete).
      - Rotate: revoke old key, create new one — caller gets new plaintext once.

    key_prefix stores the first 12 chars of the plaintext key (e.g. 'ofp_abc12345')
    so staff can identify which key is in use without storing the secret.
    """

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    name: Mapped[str] = mapped_column(Text, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    # JSON array of scope strings, e.g. ["member:read", "member:write"]
    # ["*"] means all permissions
    scopes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

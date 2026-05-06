from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, LargeBinary, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.member import Member


class DocumentTemplate(Base):
    """Registry of document templates available in this deployment.

    config_value schema:
        {
            "context": ["member_info", "benefit_estimate", ...],  # provider names
            "title": "Benefit Estimate Letter",                    # display name
            "params_schema": {"retirement_date": "date"}          # expected params
        }

    template_file is a path relative to app/templates/documents/.
    Adding a new document: add a row here + add the template file. No code needed
    unless the required context provider doesn't exist yet.
    """

    __tablename__ = "document_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    # letter | form | statement | notice
    document_type: Mapped[str] = mapped_column(String, nullable=False)
    template_file: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_value: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    generated_documents: Mapped[list[GeneratedDocument]] = relationship(back_populates="template")
    form_submissions: Mapped[list[FormSubmission]] = relationship(back_populates="template")


class GeneratedDocument(Base):
    """Audit record of every document generated.

    PDF bytes stored in `content` for audit integrity — the record reflects
    exactly what was produced and (potentially) delivered. Move to object
    storage when volume warrants it.
    """

    __tablename__ = "generated_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_templates.id"), nullable=False
    )
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), nullable=True
    )
    generated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    # generated | failed
    status: Mapped[str] = mapped_column(String, nullable=False, default="generated", server_default="'generated'")

    template: Mapped[DocumentTemplate] = relationship(back_populates="generated_documents")
    member: Mapped[Member | None] = relationship()


class FormSubmission(Base):
    """Tracks outbound forms and their return status.

    Ingest-on-return logic is deferred — this table stubs the lifecycle
    so the audit trail is in place before the e-form workflow is built.
    """

    __tablename__ = "form_submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_templates.id"), nullable=False
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), nullable=False
    )
    generated_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("generated_documents.id"), nullable=True
    )

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    return_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # sent | returned | ingested | expired | cancelled
    status: Mapped[str] = mapped_column(String, nullable=False, default="sent", server_default="'sent'")

    template: Mapped[DocumentTemplate] = relationship(back_populates="form_submissions")
    member: Mapped[Member] = relationship()
    generated_document: Mapped[GeneratedDocument | None] = relationship()

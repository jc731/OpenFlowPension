"""Document generation service.

Primary entry point: generate_for_member(slug, member_id, params, session)

The _renderer parameter is injectable for testing:
    generate_for_member(..., _renderer=lambda f, c: b"stub-pdf")
"""

import uuid
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.document import DocumentTemplate, GeneratedDocument
from app.schemas.document import DocumentTemplateCreate
from app.services.document_assembler import assemble
from app.services.document_renderer import render_to_pdf


async def get_template(slug: str, session: AsyncSession) -> DocumentTemplate:
    result = await session.execute(
        select(DocumentTemplate).where(DocumentTemplate.slug == slug, DocumentTemplate.active == True)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise ValueError(f"No active document template with slug '{slug}'")
    return template


async def list_templates(session: AsyncSession) -> list[DocumentTemplate]:
    result = await session.execute(
        select(DocumentTemplate)
        .where(DocumentTemplate.active == True)
        .order_by(DocumentTemplate.document_type, DocumentTemplate.slug)
    )
    return list(result.scalars().all())


async def create_template(data: DocumentTemplateCreate, session: AsyncSession) -> DocumentTemplate:
    existing = await session.execute(
        select(DocumentTemplate).where(DocumentTemplate.slug == data.slug)
    )
    if existing.scalar_one_or_none():
        raise ValueError(f"Template slug '{data.slug}' already exists")

    template = DocumentTemplate(
        slug=data.slug,
        document_type=data.document_type,
        template_file=data.template_file,
        description=data.description,
        config_value=data.config_value,
    )
    session.add(template)
    await session.flush()
    return template


async def generate_for_member(
    slug: str,
    member_id: uuid.UUID | None,
    params: dict,
    session: AsyncSession,
    generated_by: uuid.UUID | None = None,
    _renderer: Callable | None = None,
) -> GeneratedDocument:
    """Assemble context, render PDF, persist audit record."""
    template = await get_template(slug, session)
    context = await assemble(template, member_id, params, session)

    renderer = _renderer or render_to_pdf
    pdf_bytes = renderer(template.template_file, context)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    member_part = str(member_id)[:8] if member_id else "nomember"
    filename = f"{slug}_{member_part}_{timestamp}.pdf"

    doc = GeneratedDocument(
        template_id=template.id,
        member_id=member_id,
        generated_by=generated_by,
        params=params,
        content=pdf_bytes,
        filename=filename,
        status="generated",
    )
    session.add(doc)
    await session.flush()
    return doc


async def get_generated_document(doc_id: uuid.UUID, session: AsyncSession) -> GeneratedDocument | None:
    return await session.get(GeneratedDocument, doc_id)


async def list_member_documents(member_id: uuid.UUID, session: AsyncSession) -> list[GeneratedDocument]:
    result = await session.execute(
        select(GeneratedDocument)
        .where(GeneratedDocument.member_id == member_id)
        .options(selectinload(GeneratedDocument.template))
        .order_by(GeneratedDocument.created_at.desc())
    )
    return list(result.scalars().all())

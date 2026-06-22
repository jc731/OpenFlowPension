"""Document attachment service.

Stores file bytes to the local filesystem (ATTACHMENT_STORAGE_DIR) and
records metadata in the document_attachments table. The storage_path column
holds a path relative to ATTACHMENT_STORAGE_DIR, so the storage root can
be remounted or replaced (e.g. swapped for an S3-backed FUSE mount) without
a schema migration.

Supported entity_types: service_purchase_claim | retirement_case |
beneficiary | member | payment_batch (open string — not enforced here).
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.attachment import DocumentAttachment


def _resolve_path(storage_path: str) -> Path:
    return Path(settings.attachment_storage_dir) / storage_path


def _storage_path(entity_type: str, entity_id: uuid.UUID, file_name: str) -> str:
    """Build a relative storage path that namespaces by entity."""
    safe_name = Path(file_name).name  # strip any path traversal attempt
    return f"{entity_type}/{entity_id}/{safe_name}"


async def attach_document(
    entity_type: str,
    entity_id: uuid.UUID,
    file_bytes: bytes,
    file_name: str,
    mime_type: str,
    session: AsyncSession,
    *,
    uploaded_by: uuid.UUID | None = None,
    note: str | None = None,
) -> DocumentAttachment:
    storage_path = _storage_path(entity_type, entity_id, file_name)
    full_path = _resolve_path(storage_path)
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(file_bytes)

    attachment = DocumentAttachment(
        entity_type=entity_type,
        entity_id=entity_id,
        file_name=Path(file_name).name,
        file_size=len(file_bytes),
        mime_type=mime_type,
        storage_path=storage_path,
        uploaded_by=uploaded_by,
        note=note,
    )
    session.add(attachment)
    await session.flush()
    return attachment


async def list_attachments(
    entity_type: str,
    entity_id: uuid.UUID,
    session: AsyncSession,
) -> list[DocumentAttachment]:
    result = await session.execute(
        select(DocumentAttachment)
        .where(
            DocumentAttachment.entity_type == entity_type,
            DocumentAttachment.entity_id == entity_id,
        )
        .order_by(DocumentAttachment.created_at)
    )
    return list(result.scalars().all())


async def get_attachment(
    attachment_id: uuid.UUID,
    session: AsyncSession,
) -> DocumentAttachment | None:
    return await session.get(DocumentAttachment, attachment_id)


def read_attachment_bytes(attachment: DocumentAttachment) -> bytes:
    """Read the raw file bytes from disk. Raises FileNotFoundError if missing."""
    return _resolve_path(attachment.storage_path).read_bytes()

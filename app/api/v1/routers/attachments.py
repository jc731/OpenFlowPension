"""Document attachment endpoints.

Routes:
  POST  /attachments/{entity_type}/{entity_id}   — upload a file
  GET   /attachments/{entity_type}/{entity_id}   — list attachments for an entity
  GET   /attachments/{attachment_id}/content     — download raw file bytes
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, require_scope
from app.database import get_session
from app.services import attachment_service

router = APIRouter(prefix="/attachments", tags=["attachments"])

_VALID_ENTITY_TYPES = frozenset({
    "service_purchase_claim",
    "retirement_case",
    "beneficiary",
    "member",
    "payment_batch",
})

_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


class AttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    file_name: str
    file_size: int
    mime_type: str
    uploaded_by: uuid.UUID | None
    note: str | None
    created_at: object  # datetime


@router.post("/{entity_type}/{entity_id}", response_model=AttachmentRead, status_code=201)
async def upload_attachment(
    entity_type: str,
    entity_id: uuid.UUID,
    file: UploadFile,
    note: str | None = None,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_scope("member:write")),
):
    if entity_type not in _VALID_ENTITY_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown entity_type '{entity_type}'. Valid: {sorted(_VALID_ENTITY_TYPES)}",
        )
    file_bytes = await file.read()
    if len(file_bytes) > _MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds 20 MB limit")
    if not file.filename:
        raise HTTPException(status_code=422, detail="file_name is required")

    import uuid as _uuid
    uploaded_by_id: uuid.UUID | None = None
    try:
        uploaded_by_id = _uuid.UUID(principal["id"])
    except (ValueError, KeyError):
        pass

    async with session.begin():
        return await attachment_service.attach_document(
            entity_type=entity_type,
            entity_id=entity_id,
            file_bytes=file_bytes,
            file_name=file.filename,
            mime_type=file.content_type or "application/octet-stream",
            session=session,
            uploaded_by=uploaded_by_id,
            note=note,
        )


@router.get("/{entity_type}/{entity_id}", response_model=list[AttachmentRead],
            dependencies=[Depends(require_scope("member:read"))])
async def list_attachments(
    entity_type: str,
    entity_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    if entity_type not in _VALID_ENTITY_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown entity_type '{entity_type}'")
    return await attachment_service.list_attachments(entity_type, entity_id, session)


@router.get("/{attachment_id}/content",
            dependencies=[Depends(require_scope("member:read"))])
async def download_attachment(
    attachment_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    attachment = await attachment_service.get_attachment(attachment_id, session)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    try:
        content = attachment_service.read_attachment_bytes(attachment)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Attachment file not found on disk")
    return Response(
        content=content,
        media_type=attachment.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{attachment.file_name}"'},
    )

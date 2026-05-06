import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_scope
from app.schemas.document import (
    DocumentTemplateCreate,
    DocumentTemplateRead,
    GenerateDocumentRequest,
    GeneratedDocumentRead,
)
from app.services import document_service as svc

router = APIRouter(tags=["documents"])


@router.get("/document-templates", response_model=list[DocumentTemplateRead])
async def list_document_templates(
    session: AsyncSession = Depends(get_db),
    principal=Depends(get_current_user),
):
    require_scope(principal, "admin")
    return await svc.list_templates(session)


@router.post("/document-templates", response_model=DocumentTemplateRead, status_code=201)
async def create_document_template(
    data: DocumentTemplateCreate,
    session: AsyncSession = Depends(get_db),
    principal=Depends(get_current_user),
):
    """Register a new document template. Template file must already exist in
    app/templates/documents/. Use scripts/scaffold_document.py to create it."""
    require_scope(principal, "admin")
    try:
        template = await svc.create_template(data, session)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    await session.commit()
    return template


@router.post("/documents/generate", response_model=GeneratedDocumentRead, status_code=201)
async def generate_document(
    req: GenerateDocumentRequest,
    session: AsyncSession = Depends(get_db),
    principal=Depends(get_current_user),
):
    """Generate a document for a member and persist an audit record.
    Use GET /documents/{id}/download to retrieve the PDF."""
    require_scope(principal, "member:read")
    generated_by = uuid.UUID(principal["id"]) if principal.get("id") else None
    try:
        doc = await svc.generate_for_member(
            slug=req.slug,
            member_id=req.member_id,
            params=req.params,
            session=session,
            generated_by=generated_by,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Document generation failed: {e}")
    await session.commit()
    return doc


@router.get("/members/{member_id}/documents", response_model=list[GeneratedDocumentRead])
async def list_member_documents(
    member_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    principal=Depends(get_current_user),
):
    require_scope(principal, "member:read")
    return await svc.list_member_documents(member_id, session)


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    principal=Depends(get_current_user),
):
    """Stream the PDF bytes for a previously generated document."""
    require_scope(principal, "member:read")
    doc = await svc.get_generated_document(document_id, session)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return Response(
        content=doc.content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{doc.filename}"'},
    )

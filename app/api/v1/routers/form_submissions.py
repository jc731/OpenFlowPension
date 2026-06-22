"""Form submission lifecycle endpoints.

Routes:
  POST  /form-submissions                        — record a form as sent to a member
  GET   /form-submissions/{id}                   — get a single submission
  GET   /members/{member_id}/form-submissions    — list submissions for a member
  PATCH /form-submissions/{id}/returned          — mark a returned form as received
  PATCH /form-submissions/{id}/cancel            — cancel a submission
  PATCH /form-submissions/{id}/expire            — mark a sent form as expired
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, require_scope
from app.database import get_session
from app.services import form_submission_service

router = APIRouter(tags=["form-submissions"])


class FormSubmissionCreate(BaseModel):
    template_id: uuid.UUID
    member_id: uuid.UUID
    generated_document_id: uuid.UUID | None = None


class FormSubmissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    template_id: uuid.UUID
    member_id: uuid.UUID
    generated_document_id: uuid.UUID | None
    status: str
    sent_at: datetime | None
    returned_at: datetime | None
    return_data: dict | None
    created_at: datetime


class MarkReturnedRequest(BaseModel):
    return_data: dict[str, Any] | None = None


@router.post("/form-submissions", response_model=FormSubmissionRead, status_code=201)
async def create_form_submission(
    data: FormSubmissionCreate,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_scope("member:write")),
):
    async with session.begin():
        return await form_submission_service.create_form_submission(
            data.template_id, data.member_id, session,
            generated_document_id=data.generated_document_id,
        )


@router.get("/form-submissions/{submission_id}", response_model=FormSubmissionRead,
            dependencies=[Depends(require_scope("member:read"))])
async def get_form_submission(
    submission_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    sub = await form_submission_service.get_form_submission(submission_id, session)
    if sub is None:
        raise HTTPException(status_code=404, detail="Form submission not found")
    return sub


@router.get("/members/{member_id}/form-submissions", response_model=list[FormSubmissionRead],
            dependencies=[Depends(require_scope("member:read"))])
async def list_member_form_submissions(
    member_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    return await form_submission_service.list_member_submissions(member_id, session)


@router.patch("/form-submissions/{submission_id}/returned", response_model=FormSubmissionRead)
async def mark_returned(
    submission_id: uuid.UUID,
    body: MarkReturnedRequest,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_scope("member:write")),
):
    try:
        async with session.begin():
            return await form_submission_service.mark_returned(
                submission_id, body.return_data, session
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.patch("/form-submissions/{submission_id}/cancel", response_model=FormSubmissionRead)
async def cancel_submission(
    submission_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_scope("member:write")),
):
    try:
        async with session.begin():
            return await form_submission_service.cancel_submission(submission_id, session)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.patch("/form-submissions/{submission_id}/expire", response_model=FormSubmissionRead)
async def expire_submission(
    submission_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_scope("member:write")),
):
    try:
        async with session.begin():
            return await form_submission_service.expire_submission(submission_id, session)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

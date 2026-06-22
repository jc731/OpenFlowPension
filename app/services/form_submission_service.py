"""Form submission lifecycle service.

Tracks the outbound/inbound lifecycle of forms sent to members:

  sent → returned → ingested | expired | cancelled

The "ingest" step (parsing return_data and writing records) is per-form-type
and deliberately not built here. A registry pattern identical to CONTEXT_PROVIDERS
can be added when the first form type needs automated ingestion.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import FormSubmission


async def create_form_submission(
    template_id: uuid.UUID,
    member_id: uuid.UUID,
    session: AsyncSession,
    *,
    generated_document_id: uuid.UUID | None = None,
) -> FormSubmission:
    """Record that a form has been sent to a member."""
    submission = FormSubmission(
        template_id=template_id,
        member_id=member_id,
        generated_document_id=generated_document_id,
        status="sent",
        sent_at=datetime.now(tz=timezone.utc),
    )
    session.add(submission)
    await session.flush()
    return submission


async def get_form_submission(
    submission_id: uuid.UUID,
    session: AsyncSession,
) -> FormSubmission | None:
    return await session.get(FormSubmission, submission_id)


async def list_member_submissions(
    member_id: uuid.UUID,
    session: AsyncSession,
) -> list[FormSubmission]:
    result = await session.execute(
        select(FormSubmission)
        .where(FormSubmission.member_id == member_id)
        .order_by(FormSubmission.created_at.desc())
    )
    return list(result.scalars().all())


async def mark_returned(
    submission_id: uuid.UUID,
    return_data: dict[str, Any] | None,
    session: AsyncSession,
) -> FormSubmission:
    """Mark a form submission as returned by the member (paper or e-form).

    return_data holds the raw field values from the returned form. Parsing
    and ingestion are handled by per-form-type ingest functions (not yet built).
    """
    submission = await session.get(FormSubmission, submission_id)
    if submission is None:
        raise ValueError("Form submission not found")
    if submission.status != "sent":
        raise ValueError(
            f"Cannot mark as returned — current status is '{submission.status}'"
        )
    submission.status = "returned"
    submission.returned_at = datetime.now(tz=timezone.utc)
    submission.return_data = return_data or {}
    await session.flush()
    return submission


async def cancel_submission(
    submission_id: uuid.UUID,
    session: AsyncSession,
) -> FormSubmission:
    submission = await session.get(FormSubmission, submission_id)
    if submission is None:
        raise ValueError("Form submission not found")
    if submission.status in ("ingested", "cancelled"):
        raise ValueError(
            f"Cannot cancel a submission in status '{submission.status}'"
        )
    submission.status = "cancelled"
    await session.flush()
    return submission


async def expire_submission(
    submission_id: uuid.UUID,
    session: AsyncSession,
) -> FormSubmission:
    """Mark a sent-but-never-returned form as expired."""
    submission = await session.get(FormSubmission, submission_id)
    if submission is None:
        raise ValueError("Form submission not found")
    if submission.status != "sent":
        raise ValueError(
            f"Only 'sent' submissions can be expired; current status is '{submission.status}'"
        )
    submission.status = "expired"
    await session.flush()
    return submission

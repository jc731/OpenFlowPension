"""Accounting read endpoints.

Payment events are the accounting hook — append-only records emitted at batch
state transitions. Systems that need GL export or audit trails consume this
endpoint.
"""

import csv
import io
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_scope
from app.database import get_session
from app.schemas.payment import PaymentEventRead
from app.services import payment_events as payment_event_service

router = APIRouter(prefix="/accounting", tags=["accounting"])


@router.get(
    "/payment-events",
    response_model=list[PaymentEventRead],
    dependencies=[Depends(require_scope("admin"))],
)
async def list_payment_events(
    batch_id: uuid.UUID | None = Query(None),
    payment_id: uuid.UUID | None = Query(None),
    since: datetime | None = Query(None, description="ISO 8601 UTC datetime"),
    format: str = Query("json", description="json | csv"),
    session: AsyncSession = Depends(get_session),
):
    if format not in ("json", "csv"):
        raise HTTPException(status_code=501, detail=f"Format '{format}' is not yet implemented")

    events = await payment_event_service.list_payment_events(
        session, batch_id=batch_id, payment_id=payment_id, since=since
    )

    if format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            "id", "created_at", "event_type", "batch_id", "payment_id",
            "member_id", "amount", "gl_code", "debit_credit", "note",
        ])
        writer.writeheader()
        for e in events:
            writer.writerow({
                "id": str(e.id),
                "created_at": e.created_at.isoformat(),
                "event_type": e.event_type,
                "batch_id": str(e.batch_id) if e.batch_id else "",
                "payment_id": str(e.payment_id) if e.payment_id else "",
                "member_id": str(e.member_id) if e.member_id else "",
                "amount": str(e.amount) if e.amount is not None else "",
                "gl_code": e.gl_code or "",
                "debit_credit": e.debit_credit or "",
                "note": e.note or "",
            })
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=payment_events.csv"},
        )

    return events

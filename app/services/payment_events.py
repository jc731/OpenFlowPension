"""Payment event emission — append-only accounting hook.

PaymentEvent rows are never updated or deleted. One event per state transition
or payment action. GL codes are looked up from the 'gl_code_mapping' system
configuration key at the time of emission.

Expected gl_code_mapping shape (stored in system_configurations):
{
  "annuity": "5001",
  "refund": "5010",
  "federal_tax": "2101",
  "state_tax": "2102",
  "health_insurance": "2201",
  ...
}
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import PaymentEvent
from app.services.config_service import get_config


async def get_gl_code(type_key: str, session: AsyncSession, as_of: date | None = None) -> str | None:
    effective = as_of or date.today()
    try:
        mapping: dict = await get_config("gl_code_mapping", effective, session)
        return mapping.get(type_key)
    except Exception:
        return None


async def emit_payment_event(
    event_type: str,
    session: AsyncSession,
    *,
    batch_id: uuid.UUID | None = None,
    payment_id: uuid.UUID | None = None,
    member_id: uuid.UUID | None = None,
    amount: float | None = None,
    gl_code: str | None = None,
    debit_credit: str | None = None,
    note: str | None = None,
) -> PaymentEvent:
    event = PaymentEvent(
        batch_id=batch_id,
        payment_id=payment_id,
        member_id=member_id,
        event_type=event_type,
        amount=amount,
        gl_code=gl_code,
        debit_credit=debit_credit,
        note=note,
    )
    session.add(event)
    await session.flush()
    return event


async def list_payment_events(
    session: AsyncSession,
    *,
    batch_id: uuid.UUID | None = None,
    payment_id: uuid.UUID | None = None,
    since: datetime | None = None,
) -> list[PaymentEvent]:
    stmt = select(PaymentEvent).order_by(PaymentEvent.created_at)
    if batch_id is not None:
        stmt = stmt.where(PaymentEvent.batch_id == batch_id)
    if payment_id is not None:
        stmt = stmt.where(PaymentEvent.payment_id == payment_id)
    if since is not None:
        stmt = stmt.where(PaymentEvent.created_at >= since)
    result = await session.execute(stmt)
    return list(result.scalars().all())

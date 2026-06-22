"""Payment batch service.

Batch lifecycle: draft → net_pay_applied → dispatched → reconciled

Dispatch formats:
  json    — serialize batch + payments; return as dict
  webhook — POST the JSON payload to a caller-supplied URL
  nacha   — not yet implemented; raises NotImplementedError

total_gross / total_net are computed (not accumulated) when apply_net_pay_to_batch
transitions the batch to net_pay_applied.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import BenefitPayment, PaymentBatch
from app.services import net_pay_service
from app.services.payment_events import emit_payment_event, get_gl_code


# ── Read helpers ───────────────────────────────────────────────────────────────

async def get_batch(batch_id: uuid.UUID, session: AsyncSession) -> PaymentBatch | None:
    return await session.get(PaymentBatch, batch_id)


async def list_batches(
    session: AsyncSession,
    *,
    status: str | None = None,
    payment_type: str | None = None,
) -> list[PaymentBatch]:
    stmt = select(PaymentBatch).order_by(PaymentBatch.created_at.desc())
    if status is not None:
        stmt = stmt.where(PaymentBatch.status == status)
    if payment_type is not None:
        stmt = stmt.where(PaymentBatch.payment_type == payment_type)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ── Write operations ───────────────────────────────────────────────────────────

async def create_batch(
    payment_ids: list[uuid.UUID],
    batch_date: date,
    payment_type: str,
    session: AsyncSession,
    *,
    created_by: uuid.UUID | None = None,
    note: str | None = None,
) -> PaymentBatch:
    if not payment_ids:
        raise ValueError("payment_ids must not be empty")

    payments_result = await session.execute(
        select(BenefitPayment).where(BenefitPayment.id.in_(payment_ids))
    )
    payments = list(payments_result.scalars().all())

    found_ids = {p.id for p in payments}
    missing = [pid for pid in payment_ids if pid not in found_ids]
    if missing:
        raise ValueError(f"Payments not found: {missing}")

    already_batched = [p.id for p in payments if p.batch_id is not None]
    if already_batched:
        raise ValueError(f"Payments already assigned to a batch: {already_batched}")

    non_pending = [p.id for p in payments if p.status != "pending"]
    if non_pending:
        raise ValueError(f"Only pending payments can be added to a batch. Non-pending: {non_pending}")

    batch = PaymentBatch(
        batch_date=batch_date,
        payment_type=payment_type,
        status="draft",
        created_by=created_by,
        note=note,
    )
    session.add(batch)
    await session.flush()

    for payment in payments:
        payment.batch_id = batch.id

    await session.flush()

    gl_code = await get_gl_code(payment_type, session, as_of=batch_date)
    await emit_payment_event(
        "batch_created",
        session,
        batch_id=batch.id,
        note=f"Batch created with {len(payments)} payments",
        gl_code=gl_code,
    )

    return batch


async def apply_net_pay_to_batch(
    batch_id: uuid.UUID,
    session: AsyncSession,
    *,
    applied_by: uuid.UUID | None = None,
) -> PaymentBatch:
    batch = await session.get(PaymentBatch, batch_id)
    if batch is None:
        raise ValueError("Batch not found")
    if batch.status != "draft":
        raise ValueError(f"Cannot apply net pay to a batch in status '{batch.status}'")

    payments_result = await session.execute(
        select(BenefitPayment).where(BenefitPayment.batch_id == batch_id)
    )
    payments = list(payments_result.scalars().all())
    if not payments:
        raise ValueError("Batch has no payments")

    errors: list[str] = []
    for payment in payments:
        try:
            await net_pay_service.apply_net_pay(payment.id, session, applied_by=applied_by)
        except ValueError as exc:
            errors.append(f"Payment {payment.id}: {exc}")

    if errors:
        raise ValueError("Net pay application failed for some payments:\n" + "\n".join(errors))

    # Recompute totals from persisted values after net pay application
    await session.refresh(batch, ["payments"])
    refreshed_result = await session.execute(
        select(BenefitPayment).where(BenefitPayment.batch_id == batch_id)
    )
    refreshed_payments = list(refreshed_result.scalars().all())

    total_gross = sum(Decimal(str(p.gross_amount)) for p in refreshed_payments)
    total_net = sum(Decimal(str(p.net_amount)) for p in refreshed_payments)

    batch.total_gross = float(total_gross.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    batch.total_net = float(total_net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    batch.payment_count = len(refreshed_payments)
    batch.status = "net_pay_applied"
    await session.flush()

    gl_code = await get_gl_code(batch.payment_type, session, as_of=batch.batch_date)
    await emit_payment_event(
        "net_pay_applied",
        session,
        batch_id=batch.id,
        amount=batch.total_net,
        gl_code=gl_code,
        debit_credit="debit",
        note=f"Net pay applied to {batch.payment_count} payments",
    )

    return batch


async def dispatch_batch(
    batch_id: uuid.UUID,
    format: str,
    session: AsyncSession,
    *,
    webhook_url: str | None = None,
) -> dict:
    if format not in ("json", "webhook", "nacha"):
        raise ValueError(f"Unknown dispatch format: {format!r}")
    if format == "nacha":
        raise NotImplementedError("NACHA dispatch is not yet implemented")

    batch = await session.get(PaymentBatch, batch_id)
    if batch is None:
        raise ValueError("Batch not found")
    if batch.status != "net_pay_applied":
        raise ValueError(f"Cannot dispatch a batch in status '{batch.status}'")

    payments_result = await session.execute(
        select(BenefitPayment).where(BenefitPayment.batch_id == batch_id)
    )
    payments = list(payments_result.scalars().all())

    payload = _build_dispatch_payload(batch, payments)

    if format == "webhook":
        if not webhook_url:
            raise ValueError("webhook_url is required for webhook dispatch")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(webhook_url, json=payload)
            resp.raise_for_status()

    batch.status = "dispatched"
    batch.dispatch_format = format
    batch.dispatched_at = datetime.now(tz=timezone.utc)
    await session.flush()

    await emit_payment_event(
        "dispatched",
        session,
        batch_id=batch.id,
        amount=batch.total_net,
        note=f"Dispatched via {format}",
    )

    return payload


async def reconcile_batch(
    batch_id: uuid.UUID,
    session: AsyncSession,
) -> PaymentBatch:
    batch = await session.get(PaymentBatch, batch_id)
    if batch is None:
        raise ValueError("Batch not found")
    if batch.status != "dispatched":
        raise ValueError(f"Cannot reconcile a batch in status '{batch.status}'")

    payments_result = await session.execute(
        select(BenefitPayment).where(BenefitPayment.batch_id == batch_id)
    )
    payments = list(payments_result.scalars().all())

    now = datetime.now(tz=timezone.utc)
    for payment in payments:
        if payment.status == "pending":
            payment.status = "issued"
            payment.issued_at = now

    batch.status = "reconciled"
    batch.reconciled_at = now
    await session.flush()

    await emit_payment_event(
        "reconciled",
        session,
        batch_id=batch.id,
        amount=batch.total_net,
        note=f"Reconciled {len(payments)} payments",
    )

    return batch


# ── Serialization ──────────────────────────────────────────────────────────────

def _build_dispatch_payload(batch: PaymentBatch, payments: list[BenefitPayment]) -> dict:
    return {
        "batch_id": str(batch.id),
        "batch_date": batch.batch_date.isoformat(),
        "payment_type": batch.payment_type,
        "status": batch.status,
        "total_gross": str(batch.total_gross),
        "total_net": str(batch.total_net),
        "payment_count": batch.payment_count,
        "payments": [
            {
                "payment_id": str(p.id),
                "member_id": str(p.member_id),
                "bank_account_id": str(p.bank_account_id) if p.bank_account_id else None,
                "period_start": p.period_start.isoformat(),
                "period_end": p.period_end.isoformat(),
                "payment_date": p.payment_date.isoformat(),
                "gross_amount": str(p.gross_amount),
                "net_amount": str(p.net_amount),
                "payment_method": p.payment_method,
                "check_number": p.check_number,
            }
            for p in payments
        ],
    }

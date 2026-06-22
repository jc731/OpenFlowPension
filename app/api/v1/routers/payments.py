import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, require_scope
from app.database import get_session
from app.schemas.payment import (
    DeductionOrderCreate,
    DeductionOrderEnd,
    DeductionOrderRead,
    DispatchRequest,
    PaymentBatchCreate,
    PaymentBatchRead,
    PaymentCreate,
    PaymentEventRead,
    PaymentRead,
    PaymentReverseRequest,
    PaymentStatusUpdate,
    TaxWithholdingElectionCreate,
    TaxWithholdingElectionRead,
)
from app.services import payment_service
from app.services import batch_service
from app.services import payment_events as payment_event_service

router = APIRouter(tags=["payments"])


# ── Payments ───────────────────────────────────────────────────────────────────

@router.get("/members/{member_id}/payments", response_model=list[PaymentRead],
            dependencies=[Depends(require_scope("member:read"))])
async def list_payments(member_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    return await payment_service.list_payments(member_id, session)


@router.post("/members/{member_id}/payments", response_model=PaymentRead, status_code=201)
async def create_payment(
    member_id: uuid.UUID,
    data: PaymentCreate,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_scope("member:write")),
):
    async with session.begin():
        return await payment_service.create_payment(member_id, data, session)


@router.get("/payments/{payment_id}", response_model=PaymentRead,
            dependencies=[Depends(require_scope("member:read"))])
async def get_payment(payment_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    payment = await payment_service.get_payment(payment_id, session)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment


@router.patch("/payments/{payment_id}/status", response_model=PaymentRead)
async def update_payment_status(
    payment_id: uuid.UUID,
    data: PaymentStatusUpdate,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_scope("member:write")),
):
    try:
        async with session.begin():
            await payment_service.update_payment_status(payment_id, data, session)
        return await payment_service.get_payment(payment_id, session)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ── Deduction orders ───────────────────────────────────────────────────────────

@router.get("/members/{member_id}/deduction-orders", response_model=list[DeductionOrderRead],
            dependencies=[Depends(require_scope("member:read"))])
async def list_deduction_orders(
    member_id: uuid.UUID,
    active_only: bool = False,
    session: AsyncSession = Depends(get_session),
):
    as_of = date.today() if active_only else None
    return await payment_service.list_deduction_orders(member_id, session, active_only=active_only, as_of=as_of)


@router.post("/members/{member_id}/deduction-orders", response_model=DeductionOrderRead, status_code=201)
async def create_deduction_order(
    member_id: uuid.UUID,
    data: DeductionOrderCreate,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_scope("member:write")),
):
    async with session.begin():
        return await payment_service.create_deduction_order(member_id, data, session)


@router.patch("/members/{member_id}/deduction-orders/{order_id}/end", response_model=DeductionOrderRead)
async def end_deduction_order(
    member_id: uuid.UUID,
    order_id: uuid.UUID,
    data: DeductionOrderEnd,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_scope("member:write")),
):
    try:
        async with session.begin():
            return await payment_service.end_deduction_order(order_id, member_id, data, session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ── Tax withholding elections ──────────────────────────────────────────────────

@router.get("/members/{member_id}/tax-withholding", response_model=list[TaxWithholdingElectionRead],
            dependencies=[Depends(require_scope("member:read"))])
async def list_tax_withholding(member_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    return await payment_service.list_tax_withholding_elections(member_id, session)


@router.post("/members/{member_id}/tax-withholding", response_model=TaxWithholdingElectionRead, status_code=201)
async def set_tax_withholding(
    member_id: uuid.UUID,
    data: TaxWithholdingElectionCreate,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_scope("member:write")),
):
    async with session.begin():
        return await payment_service.set_tax_withholding(member_id, data, session)


# ── Payment reversal ───────────────────────────────────────────────────────────

@router.post("/payments/{payment_id}/reverse", response_model=PaymentRead)
async def reverse_payment(
    payment_id: uuid.UUID,
    data: PaymentReverseRequest,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_scope("member:write")),
):
    try:
        async with session.begin():
            payment = await payment_service.reverse_payment(payment_id, data.reason, session)
        return await payment_service.get_payment(payment_id, session)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ── Payment batches ────────────────────────────────────────────────────────────

@router.get("/payments/batches", response_model=list[PaymentBatchRead],
            dependencies=[Depends(require_scope("admin"))])
async def list_batches(
    status: str | None = Query(None),
    payment_type: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    return await batch_service.list_batches(session, status=status, payment_type=payment_type)


@router.post("/payments/batches", response_model=PaymentBatchRead, status_code=201)
async def create_batch(
    data: PaymentBatchCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_scope("admin")),
):
    try:
        async with session.begin():
            return await batch_service.create_batch(
                data.payment_ids,
                data.batch_date,
                data.payment_type,
                session,
                created_by=uuid.UUID(principal["id"]),
                note=data.note,
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/payments/batches/{batch_id}", response_model=PaymentBatchRead,
            dependencies=[Depends(require_scope("admin"))])
async def get_batch(batch_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    batch = await batch_service.get_batch(batch_id, session)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


@router.post("/payments/batches/{batch_id}/apply-net-pay", response_model=PaymentBatchRead)
async def apply_net_pay_to_batch(
    batch_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_scope("admin")),
):
    try:
        async with session.begin():
            return await batch_service.apply_net_pay_to_batch(
                batch_id, session, applied_by=uuid.UUID(principal["id"])
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/payments/batches/{batch_id}/dispatch", response_model=dict)
async def dispatch_batch(
    batch_id: uuid.UUID,
    data: DispatchRequest,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_scope("admin")),
):
    try:
        async with session.begin():
            payload = await batch_service.dispatch_batch(
                batch_id, data.format, session, webhook_url=data.webhook_url
            )
        return payload
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/payments/batches/{batch_id}/reconcile", response_model=PaymentBatchRead)
async def reconcile_batch(
    batch_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_scope("admin")),
):
    try:
        async with session.begin():
            return await batch_service.reconcile_batch(batch_id, session)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/payments/batches/{batch_id}/export", response_model=dict,
            dependencies=[Depends(require_scope("admin"))])
async def export_batch(
    batch_id: uuid.UUID,
    format: str = Query("json", description="json | nacha | csv"),
    session: AsyncSession = Depends(get_session),
):
    if format != "json":
        raise HTTPException(status_code=501, detail=f"Export format '{format}' is not yet implemented")
    batch = await batch_service.get_batch(batch_id, session)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    from sqlalchemy import select as sa_select
    from app.models.payment import BenefitPayment as BP
    result = await session.execute(sa_select(BP).where(BP.batch_id == batch_id))
    payments = list(result.scalars().all())
    return batch_service._build_dispatch_payload(batch, payments)

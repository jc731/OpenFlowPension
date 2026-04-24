import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, get_current_user
from app.database import get_session
from app.schemas.payment import (
    DeductionOrderCreate,
    DeductionOrderEnd,
    DeductionOrderRead,
    PaymentCreate,
    PaymentRead,
    PaymentStatusUpdate,
    TaxWithholdingElectionCreate,
    TaxWithholdingElectionRead,
)
from app.services import payment_service

router = APIRouter(tags=["payments"])


# ── Payments ───────────────────────────────────────────────────────────────────

@router.get("/members/{member_id}/payments", response_model=list[PaymentRead])
async def list_payments(member_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    return await payment_service.list_payments(member_id, session)


@router.post("/members/{member_id}/payments", response_model=PaymentRead, status_code=201)
async def create_payment(
    member_id: uuid.UUID,
    data: PaymentCreate,
    session: AsyncSession = Depends(get_session),
    current_user: Principal = Depends(get_current_user),
):
    async with session.begin():
        return await payment_service.create_payment(member_id, data, session)


@router.get("/payments/{payment_id}", response_model=PaymentRead)
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
    current_user: Principal = Depends(get_current_user),
):
    try:
        async with session.begin():
            payment = await payment_service.update_payment_status(payment_id, data, session)
        return await payment_service.get_payment(payment_id, session)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ── Deduction orders ───────────────────────────────────────────────────────────

@router.get("/members/{member_id}/deduction-orders", response_model=list[DeductionOrderRead])
async def list_deduction_orders(
    member_id: uuid.UUID,
    active_only: bool = False,
    session: AsyncSession = Depends(get_session),
):
    from datetime import date
    as_of = date.today() if active_only else None
    return await payment_service.list_deduction_orders(member_id, session, active_only=active_only, as_of=as_of)


@router.post("/members/{member_id}/deduction-orders", response_model=DeductionOrderRead, status_code=201)
async def create_deduction_order(
    member_id: uuid.UUID,
    data: DeductionOrderCreate,
    session: AsyncSession = Depends(get_session),
    current_user: Principal = Depends(get_current_user),
):
    async with session.begin():
        return await payment_service.create_deduction_order(member_id, data, session)


@router.patch("/members/{member_id}/deduction-orders/{order_id}/end", response_model=DeductionOrderRead)
async def end_deduction_order(
    member_id: uuid.UUID,
    order_id: uuid.UUID,
    data: DeductionOrderEnd,
    session: AsyncSession = Depends(get_session),
    current_user: Principal = Depends(get_current_user),
):
    try:
        async with session.begin():
            return await payment_service.end_deduction_order(order_id, member_id, data, session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ── Tax withholding elections ──────────────────────────────────────────────────

@router.get("/members/{member_id}/tax-withholding", response_model=list[TaxWithholdingElectionRead])
async def list_tax_withholding(member_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    return await payment_service.list_tax_withholding_elections(member_id, session)


@router.post("/members/{member_id}/tax-withholding", response_model=TaxWithholdingElectionRead, status_code=201)
async def set_tax_withholding(
    member_id: uuid.UUID,
    data: TaxWithholdingElectionCreate,
    session: AsyncSession = Depends(get_session),
    current_user: Principal = Depends(get_current_user),
):
    async with session.begin():
        return await payment_service.set_tax_withholding(member_id, data, session)

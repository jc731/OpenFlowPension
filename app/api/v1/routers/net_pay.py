import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_scope
from app.schemas.net_pay import (
    NetPayRequest,
    NetPayResult,
    TaxWithholdingRequest,
    TaxWithholdingResult,
)
from app.services import net_pay_service as svc
from app.services.config_service import ConfigNotFoundError

router = APIRouter(tags=["net-pay"])


@router.post("/calculate/tax-withholding", response_model=TaxWithholdingResult)
async def calculate_tax_withholding(
    req: TaxWithholdingRequest,
    session: AsyncSession = Depends(get_db),
    principal=Depends(get_current_user),
):
    """Stateless W-4P / state tax withholding calculation.

    Accepts a gross payment amount and one or more tax elections; returns the
    per-period withholding for each jurisdiction.  Federal results include all
    IRS Pub 15-T Worksheet 1B intermediate steps so the arithmetic is fully
    auditable.

    Does not read member records or apply deductions.  Use this endpoint for:
    - Member-facing W-4P calculators ("what will my withholding be?")
    - External payroll or HR systems that need IRS-accurate federal withholding
    - Verifying elections before committing them to a member's tax record
    """
    require_scope(principal, "benefit:calculate")
    try:
        return await svc.compute_tax_withholding_stateless(req, session)
    except ConfigNotFoundError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/calculate/net-pay", response_model=NetPayResult)
async def calculate_net_pay(
    req: NetPayRequest,
    session: AsyncSession = Depends(get_db),
    principal=Depends(get_current_user),
):
    """Stateless net pay calculation. Provide gross, deductions, and tax elections; get back
    a full check-stub breakdown. Does not read or write any member data."""
    require_scope(principal, "benefit:calculate")
    try:
        return await svc.calculate_net_pay_stateless(req, session)
    except ConfigNotFoundError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/payments/{payment_id}/net-pay", response_model=NetPayResult)
async def get_payment_net_pay(
    payment_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    principal=Depends(get_current_user),
):
    """Read-only. Resolves active deduction orders and W-4 elections for the payment's member
    and returns the projected check-stub breakdown. Safe to call repeatedly."""
    require_scope(principal, "benefit:calculate")
    try:
        return await svc.get_net_pay_preview(payment_id, session)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConfigNotFoundError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/payments/{payment_id}/apply-net-pay", response_model=NetPayResult)
async def apply_payment_net_pay(
    payment_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    principal=Depends(get_current_user),
):
    """Write path. Resolves and persists PaymentDeduction rows and updates net_amount on the
    payment. Idempotency guard: raises 409 if deductions are already applied."""
    require_scope(principal, "member:write")
    try:
        result = await svc.apply_net_pay(
            payment_id,
            session,
            applied_by=uuid.UUID(principal["id"]) if principal.get("id") else None,
        )
    except ValueError as e:
        msg = str(e)
        status = 409 if "already been applied" in msg else 404 if "not found" in msg else 422
        raise HTTPException(status_code=status, detail=msg)
    except ConfigNotFoundError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await session.commit()
    return result

"""Retirement case endpoints.

Routes:
  POST  /members/{member_id}/retirement-cases
  GET   /members/{member_id}/retirement-cases
  GET   /retirement-cases/{case_id}
  POST  /retirement-cases/{case_id}/recalculate
  POST  /retirement-cases/{case_id}/approve
  POST  /retirement-cases/{case_id}/activate
  POST  /retirement-cases/{case_id}/cancel
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, require_scope
from app.database import get_session
from app.services import retirement_service

router = APIRouter(tags=["retirement"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RetirementCaseCreate(BaseModel):
    retirement_date: date
    sick_leave_days: int = 0
    benefit_option_type: str = "single_life"
    beneficiary_id: uuid.UUID | None = None
    beneficiary_age_at_retirement: int | None = None
    desired_reversionary_monthly: Decimal | None = None
    note: str | None = None


class RetirementCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    member_id: uuid.UUID
    status: str
    retirement_date: date
    termination_date: date | None
    sick_leave_days: int
    benefit_option_type: str
    beneficiary_id: uuid.UUID | None
    beneficiary_age_at_retirement: int | None
    desired_reversionary_monthly: Decimal | None
    calculation_snapshot: dict[str, Any] | None
    final_monthly_annuity: Decimal | None
    first_payment_date: date | None
    first_payment_id: uuid.UUID | None
    approved_at: datetime | None
    approved_by: uuid.UUID | None
    activated_at: datetime | None
    activated_by: uuid.UUID | None
    cancelled_at: datetime | None
    cancelled_by: uuid.UUID | None
    cancel_reason: str | None
    created_by: uuid.UUID | None
    note: str | None
    created_at: datetime
    updated_at: datetime


class ApproveRequest(BaseModel):
    pass  # no extra inputs needed — all data is on the case


class ActivateRequest(BaseModel):
    first_payment_date: date
    payment_method: str = "ach"
    bank_account_id: uuid.UUID | None = None


class CancelRequest(BaseModel):
    cancel_reason: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/members/{member_id}/retirement-cases",
    response_model=RetirementCaseRead,
    status_code=201,
)
async def create_retirement_case(
    member_id: uuid.UUID,
    body: RetirementCaseCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_scope("member:write")),
):
    try:
        case = await retirement_service.create_case(
            member_id=member_id,
            retirement_date=body.retirement_date,
            session=session,
            sick_leave_days=body.sick_leave_days,
            benefit_option_type=body.benefit_option_type,
            beneficiary_id=body.beneficiary_id,
            beneficiary_age_at_retirement=body.beneficiary_age_at_retirement,
            desired_reversionary_monthly=body.desired_reversionary_monthly,
            created_by=uuid.UUID(principal["id"]) if principal.get("id") else None,
            note=body.note,
        )
        await session.commit()
        return case
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get(
    "/members/{member_id}/retirement-cases",
    response_model=list[RetirementCaseRead],
    dependencies=[Depends(require_scope("member:read"))],
)
async def list_retirement_cases(
    member_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    return await retirement_service.list_cases(member_id, session)


@router.get(
    "/retirement-cases/{case_id}",
    response_model=RetirementCaseRead,
    dependencies=[Depends(require_scope("member:read"))],
)
async def get_retirement_case(
    case_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    try:
        return await retirement_service.get_case(case_id, session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post(
    "/retirement-cases/{case_id}/recalculate",
    response_model=RetirementCaseRead,
)
async def recalculate_retirement_case(
    case_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_scope("member:write")),
):
    try:
        case = await retirement_service.recalculate(case_id, session)
        await session.commit()
        return case
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post(
    "/retirement-cases/{case_id}/approve",
    response_model=RetirementCaseRead,
)
async def approve_retirement_case(
    case_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_scope("member:write")),
):
    try:
        case = await retirement_service.approve_case(
            case_id=case_id,
            session=session,
            approved_by=uuid.UUID(principal["id"]) if principal.get("id") else None,
        )
        await session.commit()
        return case
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post(
    "/retirement-cases/{case_id}/activate",
    response_model=RetirementCaseRead,
)
async def activate_retirement_case(
    case_id: uuid.UUID,
    body: ActivateRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_scope("member:write")),
):
    try:
        case = await retirement_service.activate_case(
            case_id=case_id,
            first_payment_date=body.first_payment_date,
            session=session,
            payment_method=body.payment_method,
            bank_account_id=body.bank_account_id,
            activated_by=uuid.UUID(principal["id"]) if principal.get("id") else None,
        )
        await session.commit()
        return case
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post(
    "/retirement-cases/{case_id}/cancel",
    response_model=RetirementCaseRead,
)
async def cancel_retirement_case(
    case_id: uuid.UUID,
    body: CancelRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_scope("member:write")),
):
    try:
        case = await retirement_service.cancel_case(
            case_id=case_id,
            session=session,
            cancelled_by=uuid.UUID(principal["id"]) if principal.get("id") else None,
            cancel_reason=body.cancel_reason,
        )
        await session.commit()
        return case
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

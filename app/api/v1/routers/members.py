import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, require_scope
from app.database import get_session
from app.schemas.benefit import BenefitCalculationResult, BenefitOptionRequest
from app.schemas.member import MemberCreate, MemberRead
from app.services import benefit_estimate_service, member_service, plan_choice_service

router = APIRouter(prefix="/members", tags=["members"])


class PlanChoiceCreate(BaseModel):
    plan_tier_id: uuid.UUID
    plan_type_id: uuid.UUID
    choice_date: date


@router.get("/", response_model=list[MemberRead], dependencies=[Depends(require_scope("member:read"))])
async def list_members(session: AsyncSession = Depends(get_session)):
    return await member_service.list_members(session)


@router.get("/{member_id}", response_model=MemberRead, dependencies=[Depends(require_scope("member:read"))])
async def get_member(member_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    member = await member_service.get_member(member_id, session)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return member


@router.post("/", response_model=MemberRead, status_code=201)
async def create_member(
    data: MemberCreate,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_scope("member:write")),
):
    return await member_service.create_member(data, session)


@router.post("/{member_id}/plan-choice", response_model=MemberRead)
async def set_plan_choice(
    member_id: uuid.UUID,
    data: PlanChoiceCreate,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_scope("member:write")),
):
    try:
        async with session.begin():
            return await plan_choice_service.set_plan_choice(
                member_id, data.plan_tier_id, data.plan_type_id, data.choice_date, session
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/{member_id}/plan-choice/lock", response_model=MemberRead)
async def lock_plan_choice(
    member_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_scope("member:write")),
):
    try:
        async with session.begin():
            return await plan_choice_service.lock_plan_choice(member_id, session)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/{member_id}/benefit-estimate", response_model=BenefitCalculationResult,
            dependencies=[Depends(require_scope("member:read"))])
async def get_benefit_estimate(
    member_id: uuid.UUID,
    retirement_date: date,
    sick_leave_days: int = 0,
    benefit_option_type: str = "single_life",
    beneficiary_age: int | None = None,
    session: AsyncSession = Depends(get_session),
):
    option = BenefitOptionRequest(
        option_type=benefit_option_type,
        beneficiary_age=beneficiary_age,
    )
    try:
        return await benefit_estimate_service.get_estimate(
            member_id,
            retirement_date,
            session,
            sick_leave_days=sick_leave_days,
            benefit_option=option,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

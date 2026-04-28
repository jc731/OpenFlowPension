"""Survivor and benefit election endpoints.

Routes:
  POST   /members/{member_id}/benefit-elections
  GET    /members/{member_id}/benefit-elections/current
  GET    /members/{member_id}/survivor-benefit
  POST   /members/{member_id}/survivor-payments
"""

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, get_current_user
from app.database import get_session
from app.services import survivor_service

router = APIRouter(tags=["survivor"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class BenefitElectionCreate(BaseModel):
    option_type: str  # single_life | reversionary | js_50 | js_75 | js_100
    member_monthly_annuity: Decimal
    effective_date: date
    beneficiary_id: uuid.UUID | None = None
    beneficiary_age_at_election: int | None = None
    reversionary_monthly_amount: Decimal | None = None
    note: str | None = None


class BenefitElectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    member_id: uuid.UUID
    option_type: str
    beneficiary_id: uuid.UUID | None
    beneficiary_age_at_election: int | None
    member_monthly_annuity: Decimal
    reversionary_monthly_amount: Decimal | None
    effective_date: date
    elected_by: uuid.UUID | None
    note: str | None


class SurvivorBenefitRead(BaseModel):
    scenario: str
    is_pre_retirement: bool
    lump_sum_amount: Decimal
    survivor_monthly_amount: Decimal
    beneficiary_id: uuid.UUID | None
    option_type: str | None


class SurvivorPaymentRequest(BaseModel):
    event_date: date
    payment_method: str = "ach"


class SurvivorPaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    member_id: uuid.UUID
    beneficiary_id: uuid.UUID | None
    beneficiary_bank_account_id: uuid.UUID | None
    period_start: date
    period_end: date
    payment_date: date
    gross_amount: Decimal
    net_amount: Decimal
    payment_type: str
    payment_method: str
    status: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/members/{member_id}/benefit-elections",
    response_model=BenefitElectionRead,
    status_code=201,
)
async def create_benefit_election(
    member_id: uuid.UUID,
    body: BenefitElectionCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_user),
):
    try:
        election = await survivor_service.record_election(
            member_id=member_id,
            option_type=body.option_type,
            member_monthly_annuity=body.member_monthly_annuity,
            effective_date=body.effective_date,
            session=session,
            beneficiary_id=body.beneficiary_id,
            beneficiary_age_at_election=body.beneficiary_age_at_election,
            reversionary_monthly_amount=body.reversionary_monthly_amount,
            elected_by=uuid.UUID(principal["id"]) if principal.get("id") else None,
            note=body.note,
        )
        await session.commit()
        return election
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get(
    "/members/{member_id}/benefit-elections/current",
    response_model=BenefitElectionRead,
)
async def get_current_election(
    member_id: uuid.UUID,
    as_of: date | None = None,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_user),
):
    election = await survivor_service.get_current_election(member_id, session, as_of=as_of)
    if election is None:
        raise HTTPException(status_code=404, detail="No benefit election found for this member")
    return election


@router.get(
    "/members/{member_id}/survivor-benefit",
    response_model=SurvivorBenefitRead,
)
async def get_survivor_benefit(
    member_id: uuid.UUID,
    event_date: date,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_user),
):
    try:
        result = await survivor_service.calculate_survivor_benefit(
            member_id=member_id,
            event_date=event_date,
            session=session,
        )
        return SurvivorBenefitRead(
            scenario=result.scenario,
            is_pre_retirement=result.is_pre_retirement,
            lump_sum_amount=result.lump_sum_amount,
            survivor_monthly_amount=result.survivor_monthly_amount,
            beneficiary_id=result.beneficiary_id,
            option_type=result.option_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post(
    "/members/{member_id}/survivor-payments",
    response_model=list[SurvivorPaymentRead],
    status_code=201,
)
async def initiate_survivor_payments(
    member_id: uuid.UUID,
    body: SurvivorPaymentRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_user),
):
    try:
        payments = await survivor_service.initiate_survivor_payments(
            member_id=member_id,
            event_date=body.event_date,
            session=session,
            payment_method=body.payment_method,
            created_by=uuid.UUID(principal["id"]) if principal.get("id") else None,
        )
        await session.commit()
        return payments
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, require_scope
from app.database import get_session
from app.schemas.address import MemberAddressCreate, MemberAddressRead
from app.schemas.benefit import BenefitCalculationResult, BenefitOptionRequest
from app.schemas.contact import MemberContactCreate, MemberContactRead
from app.schemas.member import MemberCreate, MemberImportResult, MemberNameHistoryRead, MemberNameUpdate, MemberRead
from app.services import benefit_estimate_service, member_service, plan_choice_service

router = APIRouter(prefix="/members", tags=["members"])


class PlanChoiceCreate(BaseModel):
    plan_tier_id: uuid.UUID
    plan_type_id: uuid.UUID
    choice_date: date


@router.get("/", response_model=list[MemberRead], dependencies=[Depends(require_scope("member:read"))])
async def list_members(
    status: str | None = None,
    employer_id: uuid.UUID | None = None,
    employment_type: str | None = None,
    q: str | None = Query(None, description="Search name or member number"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    return await member_service.list_members(
        session,
        status=status,
        employer_id=employer_id,
        employment_type=employment_type,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.post("/import", response_model=MemberImportResult, status_code=201)
async def import_members(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_scope("member:write")),
):
    content = await file.read()
    try:
        csv_text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="File must be UTF-8 encoded CSV")
    try:
        return await member_service.bulk_import_members(csv_text, session)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


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


@router.patch("/{member_id}/name", response_model=MemberRead)
async def update_member_name(
    member_id: uuid.UUID,
    data: MemberNameUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_scope("member:write")),
):
    from app.api.deps import principal_uuid
    try:
        return await member_service.update_name(
            member_id,
            first_name=data.first_name,
            last_name=data.last_name,
            middle_name=data.middle_name,
            suffix=data.suffix,
            effective_date=data.effective_date,
            reason=data.reason,
            changed_by=principal_uuid(principal),
            session=session,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{member_id}/name-history", response_model=list[MemberNameHistoryRead],
            dependencies=[Depends(require_scope("member:read"))])
async def list_name_history(member_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    return await member_service.list_name_history(member_id, session)


@router.get("/{member_id}/addresses", response_model=list[MemberAddressRead],
            dependencies=[Depends(require_scope("member:read"))])
async def list_addresses(member_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    return await member_service.list_addresses(member_id, session)


@router.post("/{member_id}/addresses", response_model=MemberAddressRead, status_code=201)
async def add_address(
    member_id: uuid.UUID,
    data: MemberAddressCreate,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_scope("member:write")),
):
    try:
        return await member_service.add_address(member_id, data, session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{member_id}/contacts", response_model=list[MemberContactRead],
            dependencies=[Depends(require_scope("member:read"))])
async def list_contacts(member_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    return await member_service.list_contacts(member_id, session)


@router.post("/{member_id}/contacts", response_model=MemberContactRead, status_code=201)
async def add_contact(
    member_id: uuid.UUID,
    data: MemberContactCreate,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_scope("member:write")),
):
    try:
        return await member_service.add_contact(member_id, data, session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


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

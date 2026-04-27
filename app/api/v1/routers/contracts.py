import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, get_current_user
from app.database import get_session
from app.schemas.contract import (
    BeginAnnuityCreate,
    DeathRecordCreate,
    LeaveBeginCreate,
    LeaveEndCreate,
    LeavePeriodRead,
    MemberStatusHistoryRead,
    NewHireCreate,
    PercentTimeChangeCreate,
    RefundStatusCreate,
    TerminationCreate,
)
from app.schemas.employment import EmploymentRecordRead
from app.services import contract_service

router = APIRouter(tags=["contracts"])


def _user_id(current_user: Principal) -> uuid.UUID | None:
    uid = current_user["id"]
    return uuid.UUID(uid) if uid != "admin" else None


# ── Employment lifecycle ───────────────────────────────────────────────────────

@router.post("/members/{member_id}/hire", response_model=EmploymentRecordRead, status_code=201)
async def new_hire(
    member_id: uuid.UUID,
    data: NewHireCreate,
    session: AsyncSession = Depends(get_session),
    current_user: Principal = Depends(get_current_user),
):
    try:
        async with session.begin():
            return await contract_service.new_hire(member_id, data, session, created_by=_user_id(current_user))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/members/{member_id}/employment/{employment_id}/terminate", response_model=EmploymentRecordRead)
async def terminate(
    member_id: uuid.UUID,
    employment_id: uuid.UUID,
    data: TerminationCreate,
    session: AsyncSession = Depends(get_session),
    current_user: Principal = Depends(get_current_user),
):
    try:
        async with session.begin():
            return await contract_service.terminate(employment_id, member_id, data, session, changed_by=_user_id(current_user))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/members/{member_id}/employment/{employment_id}/leave/begin", response_model=LeavePeriodRead, status_code=201)
async def begin_leave(
    member_id: uuid.UUID,
    employment_id: uuid.UUID,
    data: LeaveBeginCreate,
    session: AsyncSession = Depends(get_session),
    current_user: Principal = Depends(get_current_user),
):
    try:
        async with session.begin():
            return await contract_service.begin_leave(employment_id, member_id, data, session, created_by=_user_id(current_user))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/members/{member_id}/employment/{employment_id}/leave/end", response_model=LeavePeriodRead)
async def end_leave(
    member_id: uuid.UUID,
    employment_id: uuid.UUID,
    data: LeaveEndCreate,
    session: AsyncSession = Depends(get_session),
    current_user: Principal = Depends(get_current_user),
):
    try:
        async with session.begin():
            return await contract_service.end_leave(employment_id, member_id, data, session, changed_by=_user_id(current_user))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/members/{member_id}/employment/{employment_id}/percent-time", response_model=EmploymentRecordRead)
async def change_percent_time(
    member_id: uuid.UUID,
    employment_id: uuid.UUID,
    data: PercentTimeChangeCreate,
    session: AsyncSession = Depends(get_session),
    current_user: Principal = Depends(get_current_user),
):
    try:
        async with session.begin():
            return await contract_service.change_percent_time(employment_id, member_id, data, session, changed_by=_user_id(current_user))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ── Explicit status transitions ────────────────────────────────────────────────

@router.post("/members/{member_id}/status/death", response_model=MemberStatusHistoryRead, status_code=201)
async def record_death(
    member_id: uuid.UUID,
    data: DeathRecordCreate,
    session: AsyncSession = Depends(get_session),
    current_user: Principal = Depends(get_current_user),
):
    try:
        async with session.begin():
            return await contract_service.record_death(member_id, data, session, changed_by=_user_id(current_user))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/members/{member_id}/status/begin-annuity", response_model=MemberStatusHistoryRead, status_code=201)
async def begin_annuity(
    member_id: uuid.UUID,
    data: BeginAnnuityCreate,
    session: AsyncSession = Depends(get_session),
    current_user: Principal = Depends(get_current_user),
):
    try:
        async with session.begin():
            return await contract_service.begin_annuity(member_id, data, session, changed_by=_user_id(current_user))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/members/{member_id}/status/refund", response_model=MemberStatusHistoryRead, status_code=201)
async def process_refund(
    member_id: uuid.UUID,
    data: RefundStatusCreate,
    session: AsyncSession = Depends(get_session),
    current_user: Principal = Depends(get_current_user),
):
    try:
        async with session.begin():
            return await contract_service.process_refund(member_id, data, session, changed_by=_user_id(current_user))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ── Status reads ───────────────────────────────────────────────────────────────

@router.get("/members/{member_id}/status", response_model=MemberStatusHistoryRead | None)
async def get_current_status(
    member_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    return await contract_service.get_current_status(member_id, session)


@router.get("/members/{member_id}/status/history", response_model=list[MemberStatusHistoryRead])
async def get_status_history(
    member_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    return await contract_service.get_status_history(member_id, session)

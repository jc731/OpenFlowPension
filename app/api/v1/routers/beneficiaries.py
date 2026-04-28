import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, get_current_user
from app.database import get_session
from app.services import beneficiary_service

router = APIRouter(tags=["beneficiaries"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class BeneficiaryCreate(BaseModel):
    beneficiary_type: str  # individual | estate | trust | organization
    relationship: str
    effective_date: date
    is_primary: bool = True
    # individual fields
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    ssn: str | None = None
    # estate / trust / organization
    org_name: str | None = None
    # optional on all types
    share_percent: float | None = None
    linked_member_id: uuid.UUID | None = None


class BeneficiaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    member_id: uuid.UUID
    beneficiary_type: str
    relationship: str
    is_primary: bool
    first_name: str | None
    last_name: str | None
    date_of_birth: date | None
    ssn_last_four: str | None
    org_name: str | None
    linked_member_id: uuid.UUID | None
    share_percent: float | None
    effective_date: date
    end_date: date | None


class BeneficiaryCloseRequest(BaseModel):
    end_date: date


class BeneficiaryBankAccountCreate(BaseModel):
    bank_name: str
    routing_number: str
    account_number: str
    account_last_four: str
    account_type: str  # checking | savings
    effective_date: date
    is_primary: bool = False


class BeneficiaryBankAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    beneficiary_id: uuid.UUID
    bank_name: str
    routing_number: str
    account_last_four: str
    account_type: str
    is_primary: bool
    effective_date: date
    end_date: date | None


# ---------------------------------------------------------------------------
# Beneficiary designation endpoints
# ---------------------------------------------------------------------------

@router.get("/members/{member_id}/beneficiaries", response_model=list[BeneficiaryRead])
async def list_beneficiaries(
    member_id: uuid.UUID,
    active_only: bool = False,
    is_primary: bool | None = None,
    session: AsyncSession = Depends(get_session),
):
    return await beneficiary_service.list_beneficiaries(
        member_id, session, active_only=active_only, is_primary=is_primary
    )


@router.post("/members/{member_id}/beneficiaries", response_model=BeneficiaryRead, status_code=201)
async def add_beneficiary(
    member_id: uuid.UUID,
    data: BeneficiaryCreate,
    session: AsyncSession = Depends(get_session),
    current_user: Principal = Depends(get_current_user),
):
    try:
        async with session.begin():
            return await beneficiary_service.add_beneficiary(
                member_id=member_id,
                beneficiary_type=data.beneficiary_type,
                relationship=data.relationship,
                effective_date=data.effective_date,
                is_primary=data.is_primary,
                first_name=data.first_name,
                last_name=data.last_name,
                date_of_birth=data.date_of_birth,
                ssn=data.ssn,
                org_name=data.org_name,
                share_percent=data.share_percent,
                linked_member_id=data.linked_member_id,
                session=session,
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/beneficiaries/{beneficiary_id}", response_model=BeneficiaryRead)
async def get_beneficiary(
    beneficiary_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    bene = await beneficiary_service.get_beneficiary(beneficiary_id, session)
    if not bene:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    return bene


@router.patch(
    "/members/{member_id}/beneficiaries/{beneficiary_id}/close",
    response_model=BeneficiaryRead,
)
async def close_beneficiary(
    member_id: uuid.UUID,
    beneficiary_id: uuid.UUID,
    data: BeneficiaryCloseRequest,
    session: AsyncSession = Depends(get_session),
    current_user: Principal = Depends(get_current_user),
):
    try:
        async with session.begin():
            return await beneficiary_service.close_beneficiary(
                beneficiary_id, member_id, data.end_date, session
            )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ---------------------------------------------------------------------------
# Beneficiary bank account endpoints
# ---------------------------------------------------------------------------

@router.get("/beneficiaries/{beneficiary_id}/bank-accounts", response_model=list[BeneficiaryBankAccountRead])
async def list_bank_accounts(
    beneficiary_id: uuid.UUID,
    active_only: bool = False,
    session: AsyncSession = Depends(get_session),
):
    return await beneficiary_service.list_bank_accounts(beneficiary_id, session, active_only=active_only)


@router.post("/beneficiaries/{beneficiary_id}/bank-accounts", response_model=BeneficiaryBankAccountRead, status_code=201)
async def add_bank_account(
    beneficiary_id: uuid.UUID,
    data: BeneficiaryBankAccountCreate,
    session: AsyncSession = Depends(get_session),
    current_user: Principal = Depends(get_current_user),
):
    try:
        async with session.begin():
            return await beneficiary_service.add_bank_account(
                beneficiary_id,
                bank_name=data.bank_name,
                routing_number=data.routing_number,
                account_number=data.account_number,
                account_last_four=data.account_last_four,
                account_type=data.account_type,
                effective_date=data.effective_date,
                is_primary=data.is_primary,
                session=session,
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.patch("/beneficiaries/{beneficiary_id}/bank-accounts/{account_id}/set-primary", response_model=BeneficiaryBankAccountRead)
async def set_primary(
    beneficiary_id: uuid.UUID,
    account_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: Principal = Depends(get_current_user),
):
    try:
        async with session.begin():
            return await beneficiary_service.set_primary(account_id, beneficiary_id, session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/beneficiaries/{beneficiary_id}/bank-accounts/{account_id}/close", response_model=BeneficiaryBankAccountRead)
async def close_bank_account(
    beneficiary_id: uuid.UUID,
    account_id: uuid.UUID,
    end_date: date,
    session: AsyncSession = Depends(get_session),
    current_user: Principal = Depends(get_current_user),
):
    try:
        async with session.begin():
            return await beneficiary_service.close_bank_account(account_id, beneficiary_id, end_date, session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

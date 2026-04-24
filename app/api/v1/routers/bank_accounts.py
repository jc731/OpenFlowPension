import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, get_current_user
from app.database import get_session
from app.schemas.bank_account import BankAccountCreate, BankAccountRead
from app.services import bank_account_service

router = APIRouter(prefix="/members/{member_id}/bank-accounts", tags=["bank-accounts"])


@router.get("/", response_model=list[BankAccountRead])
async def list_bank_accounts(member_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    return await bank_account_service.list_bank_accounts(member_id, session)


@router.post("/", response_model=BankAccountRead, status_code=201)
async def add_bank_account(
    member_id: uuid.UUID,
    data: BankAccountCreate,
    session: AsyncSession = Depends(get_session),
    current_user: Principal = Depends(get_current_user),
):
    async with session.begin():
        return await bank_account_service.add_bank_account(
            member_id, data, session, created_by=uuid.UUID(current_user["id"]) if current_user["id"] != "admin" else None
        )


@router.patch("/{account_id}/set-primary", response_model=BankAccountRead)
async def set_primary(
    member_id: uuid.UUID,
    account_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: Principal = Depends(get_current_user),
):
    try:
        async with session.begin():
            return await bank_account_service.set_primary(account_id, member_id, session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/{account_id}/close", response_model=BankAccountRead)
async def close_bank_account(
    member_id: uuid.UUID,
    account_id: uuid.UUID,
    end_date: str,
    session: AsyncSession = Depends(get_session),
    current_user: Principal = Depends(get_current_user),
):
    from datetime import date
    try:
        async with session.begin():
            return await bank_account_service.close_bank_account(
                account_id, member_id, date.fromisoformat(end_date), session
            )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

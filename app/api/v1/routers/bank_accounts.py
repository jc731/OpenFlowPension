import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, require_scope
from app.database import get_session
from app.schemas.bank_account import BankAccountCreate, BankAccountRead
from app.services import bank_account_service

router = APIRouter(prefix="/members/{member_id}/bank-accounts", tags=["bank-accounts"])


@router.get("/", response_model=list[BankAccountRead], dependencies=[Depends(require_scope("member:read"))])
async def list_bank_accounts(member_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    return await bank_account_service.list_bank_accounts(member_id, session)


@router.post("/", response_model=BankAccountRead, status_code=201)
async def add_bank_account(
    member_id: uuid.UUID,
    data: BankAccountCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_scope("member:write")),
):
    async with session.begin():
        return await bank_account_service.add_bank_account(
            member_id, data, session,
            created_by=uuid.UUID(principal["id"]) if principal["id"] not in ("admin", "dev-admin") else None,
        )


@router.patch("/{account_id}/set-primary", response_model=BankAccountRead)
async def set_primary(
    member_id: uuid.UUID,
    account_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_scope("member:write")),
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
    _: Principal = Depends(require_scope("member:write")),
):
    try:
        async with session.begin():
            return await bank_account_service.close_bank_account(
                account_id, member_id, date.fromisoformat(end_date), session
            )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

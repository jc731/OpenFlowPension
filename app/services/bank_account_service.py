import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import encrypt_ssn as _encrypt  # reuse Fernet encrypt/decrypt
from app.models.bank_account import MemberBankAccount
from app.schemas.bank_account import BankAccountCreate


def _encrypt_account_number(account_number: str) -> bytes:
    return _encrypt(account_number)


async def add_bank_account(
    member_id: uuid.UUID,
    data: BankAccountCreate,
    session: AsyncSession,
    created_by: uuid.UUID | None = None,
) -> MemberBankAccount:
    if data.is_primary:
        await _clear_primary(member_id, session)

    account = MemberBankAccount(
        member_id=member_id,
        bank_name=data.bank_name,
        routing_number=data.routing_number,
        account_number_encrypted=_encrypt_account_number(data.account_number),
        account_last_four=data.account_last_four,
        account_type=data.account_type,
        is_primary=data.is_primary,
        effective_date=data.effective_date,
        note=data.note,
        created_by=created_by,
    )
    session.add(account)
    await session.flush()
    return account


async def list_bank_accounts(member_id: uuid.UUID, session: AsyncSession) -> list[MemberBankAccount]:
    result = await session.execute(
        select(MemberBankAccount)
        .where(MemberBankAccount.member_id == member_id)
        .order_by(MemberBankAccount.effective_date.desc())
    )
    return list(result.scalars().all())


async def get_bank_account(account_id: uuid.UUID, session: AsyncSession) -> MemberBankAccount | None:
    return await session.get(MemberBankAccount, account_id)


async def set_primary(
    account_id: uuid.UUID,
    member_id: uuid.UUID,
    session: AsyncSession,
) -> MemberBankAccount:
    account = await session.get(MemberBankAccount, account_id)
    if not account or account.member_id != member_id:
        raise ValueError("Bank account not found for this member")
    await _clear_primary(member_id, session)
    account.is_primary = True
    await session.flush()
    return account


async def close_bank_account(
    account_id: uuid.UUID,
    member_id: uuid.UUID,
    end_date: date,
    session: AsyncSession,
) -> MemberBankAccount:
    account = await session.get(MemberBankAccount, account_id)
    if not account or account.member_id != member_id:
        raise ValueError("Bank account not found for this member")
    account.end_date = end_date
    if account.is_primary:
        account.is_primary = False
    await session.flush()
    return account


async def _clear_primary(member_id: uuid.UUID, session: AsyncSession) -> None:
    result = await session.execute(
        select(MemberBankAccount).where(
            MemberBankAccount.member_id == member_id,
            MemberBankAccount.is_primary == True,  # noqa: E712
        )
    )
    for acct in result.scalars().all():
        acct.is_primary = False

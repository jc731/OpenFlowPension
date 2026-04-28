"""Beneficiary management service.

Handles bank account management for beneficiaries — used for survivor/death
benefit payment routing. Follows the same immutability pattern as
MemberBankAccount: never update routing/account fields, add a new row instead.
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import encrypt_ssn  # reuse Fernet helper for account numbers
from app.models.beneficiary import Beneficiary, BeneficiaryBankAccount


async def add_bank_account(
    beneficiary_id: uuid.UUID,
    bank_name: str,
    routing_number: str,
    account_number: str,
    account_last_four: str,
    account_type: str,
    effective_date: date,
    is_primary: bool = False,
    session: AsyncSession = None,
    created_by: uuid.UUID | None = None,
) -> BeneficiaryBankAccount:
    beneficiary = await session.get(Beneficiary, beneficiary_id)
    if not beneficiary:
        raise ValueError(f"Beneficiary {beneficiary_id} not found")

    if is_primary:
        await _clear_primary(beneficiary_id, session)

    acct = BeneficiaryBankAccount(
        beneficiary_id=beneficiary_id,
        bank_name=bank_name,
        routing_number=routing_number,
        account_number_encrypted=encrypt_ssn(account_number),
        account_last_four=account_last_four,
        account_type=account_type,
        is_primary=is_primary,
        effective_date=effective_date,
        created_by=created_by,
    )
    session.add(acct)
    await session.flush()
    return acct


async def set_primary(
    account_id: uuid.UUID,
    beneficiary_id: uuid.UUID,
    session: AsyncSession,
) -> BeneficiaryBankAccount:
    acct = await session.get(BeneficiaryBankAccount, account_id)
    if not acct or acct.beneficiary_id != beneficiary_id:
        raise ValueError("Bank account not found for this beneficiary")
    await _clear_primary(beneficiary_id, session)
    acct.is_primary = True
    await session.flush()
    return acct


async def close_bank_account(
    account_id: uuid.UUID,
    beneficiary_id: uuid.UUID,
    end_date: date,
    session: AsyncSession,
) -> BeneficiaryBankAccount:
    acct = await session.get(BeneficiaryBankAccount, account_id)
    if not acct or acct.beneficiary_id != beneficiary_id:
        raise ValueError("Bank account not found for this beneficiary")
    acct.end_date = end_date
    acct.is_primary = False
    await session.flush()
    return acct


async def list_bank_accounts(
    beneficiary_id: uuid.UUID,
    session: AsyncSession,
    active_only: bool = False,
) -> list[BeneficiaryBankAccount]:
    stmt = select(BeneficiaryBankAccount).where(
        BeneficiaryBankAccount.beneficiary_id == beneficiary_id
    )
    if active_only:
        stmt = stmt.where(BeneficiaryBankAccount.end_date.is_(None))
    result = await session.execute(stmt.order_by(BeneficiaryBankAccount.effective_date))
    return list(result.scalars().all())


async def _clear_primary(beneficiary_id: uuid.UUID, session: AsyncSession) -> None:
    result = await session.execute(
        select(BeneficiaryBankAccount).where(
            BeneficiaryBankAccount.beneficiary_id == beneficiary_id,
            BeneficiaryBankAccount.is_primary.is_(True),
        )
    )
    for acct in result.scalars().all():
        acct.is_primary = False

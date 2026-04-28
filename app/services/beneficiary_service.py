"""Beneficiary management service.

Handles beneficiary designations and their bank accounts. Beneficiary
records are end-dated rather than deleted; close_beneficiary sets end_date.

Bank account immutability: never update routing/account fields — add a new
row and close the old one. Same Fernet encryption pattern as member bank
accounts and SSNs.
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import encrypt_ssn  # reuse Fernet helper for account numbers
from app.models.beneficiary import Beneficiary, BeneficiaryBankAccount
from app.models.member import Member

_VALID_TYPES = {"individual", "estate", "trust", "organization"}


async def add_beneficiary(
    member_id: uuid.UUID,
    beneficiary_type: str,
    relationship: str,
    effective_date: date,
    is_primary: bool = True,
    first_name: str | None = None,
    last_name: str | None = None,
    date_of_birth: date | None = None,
    ssn: str | None = None,
    org_name: str | None = None,
    share_percent: float | None = None,
    end_date: date | None = None,
    linked_member_id: uuid.UUID | None = None,
    session: AsyncSession = None,
    created_by: uuid.UUID | None = None,
) -> Beneficiary:
    if beneficiary_type not in _VALID_TYPES:
        raise ValueError(f"Invalid beneficiary_type '{beneficiary_type}'. Must be one of: {sorted(_VALID_TYPES)}")

    if beneficiary_type == "individual":
        if not first_name or not last_name:
            raise ValueError("first_name and last_name are required for individual beneficiaries")
    else:
        if not org_name:
            raise ValueError(f"org_name is required for {beneficiary_type} beneficiaries")

    member = await session.get(Member, member_id)
    if not member:
        raise ValueError(f"Member {member_id} not found")

    if linked_member_id:
        linked = await session.get(Member, linked_member_id)
        if not linked:
            raise ValueError(f"Linked member {linked_member_id} not found")

    ssn_encrypted = None
    ssn_last_four = None
    if ssn:
        ssn_encrypted = encrypt_ssn(ssn)
        ssn_last_four = ssn[-4:]

    bene = Beneficiary(
        member_id=member_id,
        beneficiary_type=beneficiary_type,
        first_name=first_name,
        last_name=last_name,
        date_of_birth=date_of_birth,
        ssn_encrypted=ssn_encrypted,
        ssn_last_four=ssn_last_four,
        org_name=org_name,
        linked_member_id=linked_member_id,
        relationship=relationship,
        share_percent=share_percent,
        is_primary=is_primary,
        effective_date=effective_date,
        end_date=end_date,
    )
    session.add(bene)
    await session.flush()
    return bene


async def get_beneficiary(
    beneficiary_id: uuid.UUID,
    session: AsyncSession,
) -> Beneficiary | None:
    return await session.get(Beneficiary, beneficiary_id)


async def list_beneficiaries(
    member_id: uuid.UUID,
    session: AsyncSession,
    active_only: bool = False,
    is_primary: bool | None = None,
) -> list[Beneficiary]:
    stmt = select(Beneficiary).where(Beneficiary.member_id == member_id)
    if active_only:
        stmt = stmt.where(Beneficiary.end_date.is_(None))
    if is_primary is not None:
        stmt = stmt.where(Beneficiary.is_primary == is_primary)
    result = await session.execute(stmt.order_by(Beneficiary.effective_date))
    return list(result.scalars().all())


async def close_beneficiary(
    beneficiary_id: uuid.UUID,
    member_id: uuid.UUID,
    end_date: date,
    session: AsyncSession,
) -> Beneficiary:
    bene = await session.get(Beneficiary, beneficiary_id)
    if not bene or bene.member_id != member_id:
        raise ValueError("Beneficiary not found for this member")
    if bene.end_date is not None:
        raise ValueError("Beneficiary designation is already closed")
    bene.end_date = end_date
    await session.flush()
    return bene


# ---------------------------------------------------------------------------
# Bank account management
# ---------------------------------------------------------------------------

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

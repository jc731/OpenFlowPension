from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import get_fernet
from app.models.third_party_entity import ThirdPartyEntity
from app.schemas.third_party_entity import ThirdPartyEntityCreate, ThirdPartyEntityUpdate


def _encrypt_account(number: str) -> bytes:
    return get_fernet().encrypt(number.encode())


async def create_entity(
    data: ThirdPartyEntityCreate,
    session: AsyncSession,
) -> ThirdPartyEntity:
    account_encrypted = None
    last_four = None
    if data.bank_account_number:
        account_encrypted = _encrypt_account(data.bank_account_number)
        last_four = data.bank_account_number[-4:]

    entity = ThirdPartyEntity(
        name=data.name,
        entity_type=data.entity_type,
        address_line1=data.address_line1,
        address_line2=data.address_line2,
        city=data.city,
        state=data.state,
        zip_code=data.zip_code,
        phone=data.phone,
        email=data.email,
        ein=data.ein,
        bank_routing_number=data.bank_routing_number,
        bank_account_number_encrypted=account_encrypted,
        bank_account_last_four=last_four,
        payment_method=data.payment_method,
        notes=data.notes,
    )
    session.add(entity)
    await session.flush()
    return entity


async def get_entity(entity_id: uuid.UUID, session: AsyncSession) -> ThirdPartyEntity | None:
    return await session.get(ThirdPartyEntity, entity_id)


async def list_entities(
    session: AsyncSession,
    active_only: bool = True,
) -> list[ThirdPartyEntity]:
    stmt = select(ThirdPartyEntity)
    if active_only:
        stmt = stmt.where(ThirdPartyEntity.active == True)  # noqa: E712
    result = await session.execute(stmt.order_by(ThirdPartyEntity.name))
    return list(result.scalars().all())


async def update_entity(
    entity_id: uuid.UUID,
    data: ThirdPartyEntityUpdate,
    session: AsyncSession,
) -> ThirdPartyEntity:
    entity = await session.get(ThirdPartyEntity, entity_id)
    if not entity:
        raise ValueError("Third-party entity not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(entity, field, value)
    await session.flush()
    return entity


async def deactivate_entity(entity_id: uuid.UUID, session: AsyncSession) -> ThirdPartyEntity:
    entity = await session.get(ThirdPartyEntity, entity_id)
    if not entity:
        raise ValueError("Third-party entity not found")
    entity.active = False
    await session.flush()
    return entity

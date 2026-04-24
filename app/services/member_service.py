import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import encrypt_ssn
from app.models.member import Member
from app.schemas.member import MemberCreate


async def create_member(data: MemberCreate, session: AsyncSession) -> Member:
    member = Member(
        ssn_encrypted=encrypt_ssn(data.ssn),
        ssn_last_four=data.ssn[-4:],
        **data.model_dump(exclude={"ssn"}),
    )
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member


async def get_member(member_id: uuid.UUID, session: AsyncSession) -> Member | None:
    result = await session.execute(select(Member).where(Member.id == member_id))
    return result.scalar_one_or_none()


async def list_members(session: AsyncSession) -> list[Member]:
    result = await session.execute(select(Member).order_by(Member.last_name, Member.first_name))
    return list(result.scalars().all())

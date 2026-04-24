import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employer import Employer
from app.schemas.employer import EmployerCreate


async def create_employer(data: EmployerCreate, session: AsyncSession) -> Employer:
    employer = Employer(**data.model_dump())
    session.add(employer)
    await session.commit()
    await session.refresh(employer)
    return employer


async def get_employer(employer_id: uuid.UUID, session: AsyncSession) -> Employer | None:
    result = await session.execute(select(Employer).where(Employer.id == employer_id))
    return result.scalar_one_or_none()


async def list_employers(session: AsyncSession) -> list[Employer]:
    result = await session.execute(select(Employer).order_by(Employer.name))
    return list(result.scalars().all())

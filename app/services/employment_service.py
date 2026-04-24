import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employment import EmploymentRecord


async def get_employment_records(member_id: uuid.UUID, session: AsyncSession) -> list[EmploymentRecord]:
    result = await session.execute(
        select(EmploymentRecord)
        .where(EmploymentRecord.member_id == member_id)
        .order_by(EmploymentRecord.hire_date)
    )
    return list(result.scalars().all())

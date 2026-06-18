import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employment import EmploymentRecord
from app.models.salary import SalaryHistory


async def get_employment_records(member_id: uuid.UUID, session: AsyncSession) -> list[EmploymentRecord]:
    result = await session.execute(
        select(EmploymentRecord)
        .where(EmploymentRecord.member_id == member_id)
        .order_by(EmploymentRecord.hire_date)
    )
    return list(result.scalars().all())


async def get_salary_history(member_id: uuid.UUID, session: AsyncSession) -> list[SalaryHistory]:
    result = await session.execute(
        select(SalaryHistory)
        .join(EmploymentRecord, SalaryHistory.employment_id == EmploymentRecord.id)
        .where(EmploymentRecord.member_id == member_id)
        .order_by(SalaryHistory.effective_date.desc())
    )
    return list(result.scalars().all())

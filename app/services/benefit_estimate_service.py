"""DB-backed benefit estimate service.

Assembles a BenefitCalculationRequest from real member data and delegates
to the stateless calculation engine. Read-only — no DB writes.

Staff use this to run a calculation against posted data without having to
manually assemble the request. Members self-service estimates (with salary
projections) are a separate future feature.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employment import EmploymentRecord
from app.models.member import Member
from app.models.payroll import ContributionRecord
from app.models.plan_config import PlanType
from app.models.salary import SalaryHistory
from app.models.service_credit import ServiceCreditEntry
from app.schemas.benefit import (
    BenefitCalculationRequest,
    BenefitCalculationResult,
    BenefitOptionRequest,
    MoneyPurchaseContributions,
    SalaryPeriod,
)
from app.services.benefit.calculator import calculate_benefit


async def get_estimate(
    member_id: uuid.UUID,
    retirement_date: date,
    session: AsyncSession,
    sick_leave_days: int = 0,
    benefit_option: BenefitOptionRequest | None = None,
) -> BenefitCalculationResult:
    member = await session.get(Member, member_id)
    if not member:
        raise ValueError(f"Member {member_id} not found")

    if not member.certification_date:
        raise ValueError("Member has no certification date — cannot calculate benefit")

    if not member.plan_type_id:
        raise ValueError("Member has no plan choice on record — cannot calculate benefit")

    plan_type_obj = await session.get(PlanType, member.plan_type_id)
    plan_type_str = plan_type_obj.plan_code.lower()
    if plan_type_str not in ("traditional", "portable"):
        raise ValueError(f"Unrecognized plan_code '{plan_type_obj.plan_code}' — expected traditional or portable")

    termination_date = await _latest_termination_date(member_id, session) or retirement_date

    salary_periods = await _salary_periods(member_id, session)
    if not salary_periods:
        raise ValueError("No salary history found for this member — cannot calculate benefit")

    surs_service_years = await _total_service_credit(member_id, session)
    mp_contributions = await _mp_contributions(member_id, session)
    is_police_fire = await _is_police_fire(member_id, session)

    request = BenefitCalculationRequest(
        member_id=member_id,
        plan_type=plan_type_str,
        cert_date=member.certification_date,
        birth_date=member.date_of_birth,
        retirement_date=retirement_date,
        termination_date=termination_date,
        surs_service_years=Decimal(str(surs_service_years)),
        sick_leave_days=sick_leave_days,
        salary_history=salary_periods,
        money_purchase_contributions=mp_contributions,
        is_police_fire=is_police_fire,
        benefit_option=benefit_option,
    )

    return calculate_benefit(request)


async def _latest_termination_date(member_id: uuid.UUID, session: AsyncSession) -> date | None:
    stmt = (
        select(EmploymentRecord.termination_date)
        .where(
            EmploymentRecord.member_id == member_id,
            EmploymentRecord.termination_date.isnot(None),
        )
        .order_by(EmploymentRecord.termination_date.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _salary_periods(member_id: uuid.UUID, session: AsyncSession) -> list[SalaryPeriod]:
    stmt = (
        select(SalaryHistory)
        .join(EmploymentRecord, SalaryHistory.employment_id == EmploymentRecord.id)
        .where(EmploymentRecord.member_id == member_id)
        .order_by(SalaryHistory.effective_date)
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()
    return [
        SalaryPeriod(
            start_date=row.effective_date,
            end_date=row.end_date,
            annual_salary=Decimal(str(row.annual_salary)),
        )
        for row in rows
    ]


async def _total_service_credit(member_id: uuid.UUID, session: AsyncSession) -> Decimal:
    stmt = select(func.sum(ServiceCreditEntry.credit_years)).where(
        ServiceCreditEntry.member_id == member_id,
        ServiceCreditEntry.voided_at.is_(None),
    )
    result = await session.execute(stmt)
    total = result.scalar_one_or_none()
    return Decimal(str(total)) if total is not None else Decimal("0")


async def _mp_contributions(member_id: uuid.UUID, session: AsyncSession) -> MoneyPurchaseContributions:
    stmt = (
        select(
            ContributionRecord.contribution_type,
            func.sum(
                ContributionRecord.employee_contribution + ContributionRecord.employer_contribution
            ),
        )
        .where(
            ContributionRecord.member_id == member_id,
            ContributionRecord.voided_at.is_(None),
        )
        .group_by(ContributionRecord.contribution_type)
    )
    result = await session.execute(stmt)
    by_type = {row[0]: Decimal(str(row[1])) for row in result.all()}
    return MoneyPurchaseContributions(
        normal_ci=by_type.get("normal", Decimal("0")),
        ope_ci=by_type.get("ope", Decimal("0")),
        military_ci=by_type.get("military", Decimal("0")),
    )


async def _is_police_fire(member_id: uuid.UUID, session: AsyncSession) -> bool:
    stmt = select(EmploymentRecord.id).where(
        EmploymentRecord.member_id == member_id,
        EmploymentRecord.employment_type == "police_fire",
    ).limit(1)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None

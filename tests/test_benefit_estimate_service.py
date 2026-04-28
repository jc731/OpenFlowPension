"""Tests for the DB-backed benefit estimate service."""

from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employer import Employer
from app.models.employment import EmploymentRecord
from app.models.member import Member
from app.models.plan_config import PlanTier, PlanType
from app.models.salary import SalaryHistory
from app.models.service_credit import ServiceCreditEntry
from app.services import benefit_estimate_service

pytestmark = pytest.mark.asyncio

RETIREMENT_DATE = date(2025, 1, 15)


# ---------------------------------------------------------------------------
# Fixtures — minimal Jane Smith scenario
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def plan_type(session: AsyncSession) -> PlanType:
    pt = PlanType(plan_code="traditional", plan_label="Traditional")
    session.add(pt)
    await session.flush()
    return pt


@pytest_asyncio.fixture
async def plan_tier(session: AsyncSession) -> PlanTier:
    tier = PlanTier(
        tier_code="TIER_I",
        tier_label="Tier I",
        effective_date=date(2000, 1, 1),
    )
    session.add(tier)
    await session.flush()
    return tier


@pytest_asyncio.fixture
async def employer(session: AsyncSession) -> Employer:
    emp = Employer(
        name="State University",
        employer_code="SU001",
        employer_type="university",
    )
    session.add(emp)
    await session.flush()
    return emp


@pytest_asyncio.fixture
async def member(session: AsyncSession, plan_tier: PlanTier, plan_type: PlanType) -> Member:
    from app.crypto import encrypt_ssn
    m = Member(
        member_number="E001",
        first_name="Jane",
        last_name="Smith",
        date_of_birth=date(1965, 3, 15),
        ssn_encrypted=encrypt_ssn("123-45-6789"),
        ssn_last_four="6789",
        certification_date=date(2000, 1, 15),
        plan_tier_id=plan_tier.id,
        plan_type_id=plan_type.id,
        plan_choice_date=date(2000, 3, 1),
        plan_choice_locked=True,
    )
    session.add(m)
    await session.flush()
    return m


@pytest_asyncio.fixture
async def employment(session: AsyncSession, member: Member, employer: Employer) -> EmploymentRecord:
    emp = EmploymentRecord(
        member_id=member.id,
        employer_id=employer.id,
        employment_type="general_staff",
        hire_date=date(2000, 1, 15),
        percent_time=100.0,
    )
    session.add(emp)
    await session.flush()
    return emp


@pytest_asyncio.fixture
async def salary_history(session: AsyncSession, employment: EmploymentRecord):
    rows = [
        SalaryHistory(
            employment_id=employment.id,
            effective_date=date(2000, 1, 15),
            end_date=date(2009, 12, 31),
            annual_salary=40000,
        ),
        SalaryHistory(
            employment_id=employment.id,
            effective_date=date(2010, 1, 1),
            end_date=date(2024, 12, 31),
            annual_salary=60000,
        ),
        SalaryHistory(
            employment_id=employment.id,
            effective_date=date(2025, 1, 1),
            end_date=None,
            annual_salary=65000,
        ),
    ]
    session.add_all(rows)
    await session.flush()
    return rows


@pytest_asyncio.fixture
async def service_credit(session: AsyncSession, member: Member, employment: EmploymentRecord):
    entry = ServiceCreditEntry(
        member_id=member.id,
        employment_id=employment.id,
        entry_type="regular",
        credit_days=365 * 25,
        credit_years=25.0,
        period_start=date(2000, 1, 15),
        period_end=date(2025, 1, 15),
    )
    session.add(entry)
    await session.flush()
    return entry


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_estimate_returns_result(
    session: AsyncSession, member: Member, salary_history, service_credit
):
    result = await benefit_estimate_service.get_estimate(
        member.id, RETIREMENT_DATE, session
    )

    assert result.member_id == member.id
    assert result.retirement_date == RETIREMENT_DATE
    assert result.tier in ("I", "II")
    assert result.final_monthly_annuity > 0


async def test_estimate_respects_sick_leave(
    session: AsyncSession, member: Member, salary_history, service_credit
):
    no_sick = await benefit_estimate_service.get_estimate(
        member.id, RETIREMENT_DATE, session, sick_leave_days=0
    )
    with_sick = await benefit_estimate_service.get_estimate(
        member.id, RETIREMENT_DATE, session, sick_leave_days=180
    )
    # More sick leave = more service credit = higher benefit
    assert with_sick.final_monthly_annuity >= no_sick.final_monthly_annuity


async def test_estimate_member_not_found(session: AsyncSession):
    import uuid
    with pytest.raises(ValueError, match="not found"):
        await benefit_estimate_service.get_estimate(uuid.uuid4(), RETIREMENT_DATE, session)


async def test_estimate_missing_certification_date(
    session: AsyncSession, plan_tier: PlanTier, plan_type: PlanType, salary_history, service_credit
):
    from app.crypto import encrypt_ssn
    m = Member(
        member_number="E002",
        first_name="No",
        last_name="Cert",
        date_of_birth=date(1970, 1, 1),
        ssn_encrypted=encrypt_ssn("000-00-0001"),
        ssn_last_four="0001",
        plan_type_id=plan_type.id,
        plan_tier_id=plan_tier.id,
        # certification_date intentionally omitted
    )
    session.add(m)
    await session.flush()

    with pytest.raises(ValueError, match="certification date"):
        await benefit_estimate_service.get_estimate(m.id, RETIREMENT_DATE, session)


async def test_estimate_missing_plan_choice(
    session: AsyncSession, salary_history, service_credit
):
    from app.crypto import encrypt_ssn
    m = Member(
        member_number="E003",
        first_name="No",
        last_name="Plan",
        date_of_birth=date(1970, 1, 1),
        ssn_encrypted=encrypt_ssn("000-00-0002"),
        ssn_last_four="0002",
        certification_date=date(2000, 1, 1),
        # plan_type_id intentionally omitted
    )
    session.add(m)
    await session.flush()

    with pytest.raises(ValueError, match="plan choice"):
        await benefit_estimate_service.get_estimate(m.id, RETIREMENT_DATE, session)


async def test_estimate_no_salary_history(
    session: AsyncSession, member: Member, service_credit
):
    # salary_history fixture not included — member has no salary rows
    with pytest.raises(ValueError, match="salary history"):
        await benefit_estimate_service.get_estimate(member.id, RETIREMENT_DATE, session)


async def test_estimate_uses_termination_date(
    session: AsyncSession, member: Member, employer: Employer,
    salary_history, service_credit
):
    # Add a terminated employment record
    terminated_emp = EmploymentRecord(
        member_id=member.id,
        employer_id=employer.id,
        employment_type="general_staff",
        hire_date=date(2000, 1, 15),
        termination_date=date(2024, 6, 30),
        percent_time=100.0,
    )
    session.add(terminated_emp)
    await session.flush()

    result = await benefit_estimate_service.get_estimate(
        member.id, RETIREMENT_DATE, session
    )
    # Engine should not raise — termination_date is taken from the employment record
    assert result.final_monthly_annuity > 0


async def test_estimate_police_fire_detected(
    session: AsyncSession, member: Member, employer: Employer,
    salary_history, service_credit
):
    pf_emp = EmploymentRecord(
        member_id=member.id,
        employer_id=employer.id,
        employment_type="police_fire",
        hire_date=date(2000, 1, 15),
        percent_time=100.0,
    )
    session.add(pf_emp)
    await session.flush()

    # Police/fire employment is detected; formula shows applicable only when
    # police_fire_service_years > 0. With no P/F service credit entries, the
    # engine correctly returns applicable=False — verify the call succeeds.
    result = await benefit_estimate_service.get_estimate(
        member.id, RETIREMENT_DATE, session
    )
    assert result.final_monthly_annuity > 0
    assert result.formulas.police_fire is not None

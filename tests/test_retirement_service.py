"""Tests for the retirement case management service.

These tests exercise the full create → approve → activate lifecycle against a
real test database using the same Jane Smith scenario as the estimate tests.
"""

from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.beneficiary import Beneficiary
from app.models.employer import Employer
from app.models.employment import EmploymentRecord
from app.models.member import Member
from app.models.plan_config import PlanTier, PlanType
from app.models.retirement_case import RetirementCase
from app.models.salary import SalaryHistory
from app.models.service_credit import ServiceCreditEntry
from app.services import retirement_service

pytestmark = pytest.mark.asyncio

RETIREMENT_DATE = date(2025, 1, 15)


# ---------------------------------------------------------------------------
# Fixtures — Jane Smith 25-year scenario
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
        employer_code="RC001",
        employer_type="university",
    )
    session.add(emp)
    await session.flush()
    return emp


@pytest_asyncio.fixture
async def member(session: AsyncSession, plan_tier: PlanTier, plan_type: PlanType) -> Member:
    from app.crypto import encrypt_ssn
    m = Member(
        member_number="RC001",
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
        member_status="terminated",
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
        termination_date=date(2025, 1, 14),
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
            end_date=date(2025, 1, 14),
            annual_salary=60000,
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
        period_end=date(2025, 1, 14),
    )
    session.add(entry)
    await session.flush()
    return entry


@pytest_asyncio.fixture
async def ready_member(
    session, member, employment, salary_history, service_credit
) -> Member:
    """Member with all data needed to create a retirement case."""
    return member


@pytest_asyncio.fixture
async def draft_case(session: AsyncSession, ready_member: Member) -> RetirementCase:
    return await retirement_service.create_case(
        member_id=ready_member.id,
        retirement_date=RETIREMENT_DATE,
        session=session,
    )


@pytest_asyncio.fixture
async def approved_case(session: AsyncSession, draft_case: RetirementCase) -> RetirementCase:
    return await retirement_service.approve_case(draft_case.id, session)


# ---------------------------------------------------------------------------
# create_case
# ---------------------------------------------------------------------------

async def test_create_case_produces_draft(session: AsyncSession, ready_member: Member):
    case = await retirement_service.create_case(
        member_id=ready_member.id,
        retirement_date=RETIREMENT_DATE,
        session=session,
    )
    assert case.status == "draft"
    assert case.member_id == ready_member.id
    assert case.retirement_date == RETIREMENT_DATE
    assert case.calculation_snapshot is not None
    assert case.final_monthly_annuity is None  # not set until approval


async def test_create_case_snapshot_has_positive_annuity(session: AsyncSession, ready_member: Member):
    case = await retirement_service.create_case(
        member_id=ready_member.id,
        retirement_date=RETIREMENT_DATE,
        session=session,
    )
    snapshot = case.calculation_snapshot
    assert snapshot is not None
    assert float(snapshot["final_monthly_annuity"]) > 0


async def test_create_case_stores_termination_date(session: AsyncSession, ready_member: Member):
    case = await retirement_service.create_case(
        member_id=ready_member.id,
        retirement_date=RETIREMENT_DATE,
        session=session,
    )
    # Termination date should be picked up from the employment record
    assert case.termination_date == date(2025, 1, 14)


async def test_create_case_rejects_annuitant(session: AsyncSession, ready_member: Member):
    ready_member.member_status = "annuitant"
    await session.flush()
    with pytest.raises(ValueError, match="already an annuitant"):
        await retirement_service.create_case(
            member_id=ready_member.id,
            retirement_date=RETIREMENT_DATE,
            session=session,
        )


async def test_create_case_rejects_deceased(session: AsyncSession, ready_member: Member):
    ready_member.member_status = "deceased"
    await session.flush()
    with pytest.raises(ValueError, match="deceased"):
        await retirement_service.create_case(
            member_id=ready_member.id,
            retirement_date=RETIREMENT_DATE,
            session=session,
        )


async def test_create_case_rejects_duplicate_open_case(session: AsyncSession, ready_member: Member):
    await retirement_service.create_case(
        member_id=ready_member.id,
        retirement_date=RETIREMENT_DATE,
        session=session,
    )
    with pytest.raises(ValueError, match="already has an open retirement case"):
        await retirement_service.create_case(
            member_id=ready_member.id,
            retirement_date=RETIREMENT_DATE,
            session=session,
        )


async def test_create_case_allowed_after_cancellation(session: AsyncSession, ready_member: Member):
    case1 = await retirement_service.create_case(
        member_id=ready_member.id,
        retirement_date=RETIREMENT_DATE,
        session=session,
    )
    await retirement_service.cancel_case(case1.id, session)

    case2 = await retirement_service.create_case(
        member_id=ready_member.id,
        retirement_date=RETIREMENT_DATE,
        session=session,
    )
    assert case2.status == "draft"


# ---------------------------------------------------------------------------
# recalculate
# ---------------------------------------------------------------------------

async def test_recalculate_updates_snapshot(session: AsyncSession, draft_case: RetirementCase):
    original_snapshot = draft_case.calculation_snapshot
    case = await retirement_service.recalculate(draft_case.id, session)
    # Snapshot should be refreshed (still valid, same structure)
    assert case.calculation_snapshot is not None
    assert "final_monthly_annuity" in case.calculation_snapshot


async def test_recalculate_rejected_on_approved(session: AsyncSession, approved_case: RetirementCase):
    with pytest.raises(ValueError, match="must be draft"):
        await retirement_service.recalculate(approved_case.id, session)


# ---------------------------------------------------------------------------
# approve_case
# ---------------------------------------------------------------------------

async def test_approve_case_sets_final_annuity(session: AsyncSession, draft_case: RetirementCase):
    case = await retirement_service.approve_case(draft_case.id, session)
    assert case.status == "approved"
    assert case.final_monthly_annuity is not None
    assert case.final_monthly_annuity > 0
    assert case.approved_at is not None


async def test_approve_case_transitions_member_to_annuitant(
    session: AsyncSession, draft_case: RetirementCase, ready_member: Member
):
    await retirement_service.approve_case(draft_case.id, session)
    await session.refresh(ready_member)
    assert ready_member.member_status == "annuitant"


async def test_approve_case_records_single_life_election(
    session: AsyncSession, draft_case: RetirementCase
):
    from app.services import survivor_service
    await retirement_service.approve_case(draft_case.id, session)
    election = await survivor_service.get_current_election(draft_case.member_id, session)
    assert election is not None
    assert election.option_type == "single_life"


async def test_approve_rejected_on_already_approved(
    session: AsyncSession, approved_case: RetirementCase
):
    with pytest.raises(ValueError, match="must be draft"):
        await retirement_service.approve_case(approved_case.id, session)


async def test_approve_requires_snapshot(session: AsyncSession, ready_member: Member):
    case = await retirement_service.create_case(
        member_id=ready_member.id,
        retirement_date=RETIREMENT_DATE,
        session=session,
    )
    # Manually clear snapshot to simulate missing data
    case.calculation_snapshot = None
    await session.flush()

    with pytest.raises(ValueError, match="no calculation snapshot"):
        await retirement_service.approve_case(case.id, session)


# ---------------------------------------------------------------------------
# activate_case
# ---------------------------------------------------------------------------

async def test_activate_case_creates_payment(
    session: AsyncSession, approved_case: RetirementCase
):
    case = await retirement_service.activate_case(
        case_id=approved_case.id,
        first_payment_date=date(2025, 2, 1),
        session=session,
    )
    assert case.status == "active"
    assert case.first_payment_id is not None
    assert case.first_payment_date == date(2025, 2, 1)
    assert case.activated_at is not None


async def test_activate_payment_has_correct_type_and_amount(
    session: AsyncSession, approved_case: RetirementCase
):
    from app.models.payment import BenefitPayment
    case = await retirement_service.activate_case(
        case_id=approved_case.id,
        first_payment_date=date(2025, 2, 1),
        session=session,
    )
    payment = await session.get(BenefitPayment, case.first_payment_id)
    assert payment is not None
    assert payment.payment_type == "annuity"
    assert payment.gross_amount == case.final_monthly_annuity
    assert payment.status == "pending"


async def test_activate_rejected_on_draft(session: AsyncSession, draft_case: RetirementCase):
    with pytest.raises(ValueError, match="must be approved"):
        await retirement_service.activate_case(
            case_id=draft_case.id,
            first_payment_date=date(2025, 2, 1),
            session=session,
        )


async def test_activate_rejected_on_active(
    session: AsyncSession, approved_case: RetirementCase
):
    await retirement_service.activate_case(
        case_id=approved_case.id,
        first_payment_date=date(2025, 2, 1),
        session=session,
    )
    with pytest.raises(ValueError, match="must be approved"):
        await retirement_service.activate_case(
            case_id=approved_case.id,
            first_payment_date=date(2025, 3, 1),
            session=session,
        )


# ---------------------------------------------------------------------------
# cancel_case
# ---------------------------------------------------------------------------

async def test_cancel_draft_case(session: AsyncSession, draft_case: RetirementCase):
    case = await retirement_service.cancel_case(
        draft_case.id, session, cancel_reason="Member withdrew request"
    )
    assert case.status == "cancelled"
    assert case.cancel_reason == "Member withdrew request"
    assert case.cancelled_at is not None


async def test_cancel_approved_case(session: AsyncSession, approved_case: RetirementCase):
    case = await retirement_service.cancel_case(approved_case.id, session)
    assert case.status == "cancelled"


async def test_cancel_active_case_rejected(
    session: AsyncSession, approved_case: RetirementCase
):
    await retirement_service.activate_case(
        case_id=approved_case.id,
        first_payment_date=date(2025, 2, 1),
        session=session,
    )
    with pytest.raises(ValueError, match="Cannot cancel"):
        await retirement_service.cancel_case(approved_case.id, session)


# ---------------------------------------------------------------------------
# list_cases / get_case
# ---------------------------------------------------------------------------

async def test_list_cases_returns_all(session: AsyncSession, ready_member: Member):
    case1 = await retirement_service.create_case(
        member_id=ready_member.id,
        retirement_date=RETIREMENT_DATE,
        session=session,
    )
    await retirement_service.cancel_case(case1.id, session)

    case2 = await retirement_service.create_case(
        member_id=ready_member.id,
        retirement_date=RETIREMENT_DATE,
        session=session,
    )

    cases = await retirement_service.list_cases(ready_member.id, session)
    assert len(cases) == 2


async def test_get_case_not_found(session: AsyncSession):
    import uuid
    with pytest.raises(ValueError, match="not found"):
        await retirement_service.get_case(uuid.uuid4(), session)

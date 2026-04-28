"""Tests for death and survivor benefit service."""

from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.beneficiary import Beneficiary, BeneficiaryBankAccount
from app.models.member import Member
from app.models.payroll import ContributionRecord
from app.services import survivor_service

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def member(session: AsyncSession) -> Member:
    from app.crypto import encrypt_ssn
    m = Member(
        member_number="SV001",
        first_name="Jane",
        last_name="Smith",
        date_of_birth=date(1965, 3, 15),
        ssn_encrypted=encrypt_ssn("123-45-6789"),
        ssn_last_four="6789",
        member_status="active",
    )
    session.add(m)
    await session.flush()
    return m


@pytest_asyncio.fixture
async def annuitant(session: AsyncSession) -> Member:
    from app.crypto import encrypt_ssn
    m = Member(
        member_number="SV002",
        first_name="Robert",
        last_name="Smith",
        date_of_birth=date(1960, 6, 1),
        ssn_encrypted=encrypt_ssn("555-44-3333"),
        ssn_last_four="3333",
        member_status="annuitant",
    )
    session.add(m)
    await session.flush()
    return m


@pytest_asyncio.fixture
async def beneficiary(session: AsyncSession, annuitant: Member) -> Beneficiary:
    from app.crypto import encrypt_ssn
    b = Beneficiary(
        member_id=annuitant.id,
        beneficiary_type="individual",
        first_name="Alice",
        last_name="Smith",
        date_of_birth=date(1962, 4, 10),
        ssn_encrypted=encrypt_ssn("111-22-3333"),
        ssn_last_four="3333",
        relationship="spouse",
        is_primary=True,
        effective_date=date(2000, 1, 1),
    )
    session.add(b)
    await session.flush()
    return b


@pytest_asyncio.fixture
async def bene_bank_account(session: AsyncSession, beneficiary: Beneficiary) -> BeneficiaryBankAccount:
    from app.crypto import encrypt_ssn
    acct = BeneficiaryBankAccount(
        beneficiary_id=beneficiary.id,
        bank_name="First Bank",
        routing_number="071000013",
        account_number_encrypted=encrypt_ssn("12345678"),
        account_last_four="5678",
        account_type="checking",
        is_primary=True,
        effective_date=date(2020, 1, 1),
    )
    session.add(acct)
    await session.flush()
    return acct


@pytest_asyncio.fixture
async def member_with_contributions(session: AsyncSession, member: Member) -> Member:
    from app.models.employer import Employer
    employer = Employer(
        employer_code="E001",
        name="State University",
        employer_type="university",
    )
    session.add(employer)
    await session.flush()

    from app.models.employment import EmploymentRecord
    emp = EmploymentRecord(
        member_id=member.id,
        employer_id=employer.id,
        employment_type="general_staff",
        hire_date=date(2000, 1, 15),
        percent_time=Decimal("100.00"),
    )
    session.add(emp)
    await session.flush()

    for year in range(2000, 2010):
        cr = ContributionRecord(
            member_id=member.id,
            employment_id=emp.id,
            period_start=date(year, 1, 1),
            period_end=date(year, 12, 31),
            employee_contribution=Decimal("4000"),
            employer_contribution=Decimal("2000"),
        )
        session.add(cr)
    await session.flush()
    return member


# ---------------------------------------------------------------------------
# record_election
# ---------------------------------------------------------------------------

async def test_record_election_single_life(session: AsyncSession, annuitant: Member):
    election = await survivor_service.record_election(
        member_id=annuitant.id,
        option_type="single_life",
        member_monthly_annuity=Decimal("2000.00"),
        effective_date=date(2025, 1, 1),
        session=session,
    )
    assert election.option_type == "single_life"
    assert election.member_monthly_annuity == Decimal("2000.00")
    assert election.beneficiary_id is None


async def test_record_election_js_50(session: AsyncSession, annuitant: Member, beneficiary: Beneficiary):
    election = await survivor_service.record_election(
        member_id=annuitant.id,
        option_type="js_50",
        member_monthly_annuity=Decimal("1900.00"),
        effective_date=date(2025, 1, 1),
        session=session,
        beneficiary_id=beneficiary.id,
        beneficiary_age_at_election=62,
    )
    assert election.option_type == "js_50"
    assert election.beneficiary_id == beneficiary.id
    assert election.beneficiary_age_at_election == 62


async def test_record_election_reversionary(session: AsyncSession, annuitant: Member, beneficiary: Beneficiary):
    election = await survivor_service.record_election(
        member_id=annuitant.id,
        option_type="reversionary",
        member_monthly_annuity=Decimal("1850.00"),
        effective_date=date(2025, 1, 1),
        session=session,
        beneficiary_id=beneficiary.id,
        reversionary_monthly_amount=Decimal("500.00"),
    )
    assert election.option_type == "reversionary"
    assert election.reversionary_monthly_amount == Decimal("500.00")


async def test_record_election_requires_beneficiary_for_js(session: AsyncSession, annuitant: Member):
    with pytest.raises(ValueError, match="requires a beneficiary_id"):
        await survivor_service.record_election(
            member_id=annuitant.id,
            option_type="js_50",
            member_monthly_annuity=Decimal("1900.00"),
            effective_date=date(2025, 1, 1),
            session=session,
        )


async def test_record_election_requires_amount_for_reversionary(
    session: AsyncSession, annuitant: Member, beneficiary: Beneficiary
):
    with pytest.raises(ValueError, match="requires reversionary_monthly_amount"):
        await survivor_service.record_election(
            member_id=annuitant.id,
            option_type="reversionary",
            member_monthly_annuity=Decimal("1850.00"),
            effective_date=date(2025, 1, 1),
            session=session,
            beneficiary_id=beneficiary.id,
        )


async def test_record_election_rejects_invalid_option(session: AsyncSession, annuitant: Member):
    with pytest.raises(ValueError, match="Invalid option_type"):
        await survivor_service.record_election(
            member_id=annuitant.id,
            option_type="js_999",
            member_monthly_annuity=Decimal("1900.00"),
            effective_date=date(2025, 1, 1),
            session=session,
        )


async def test_record_election_rejects_wrong_member_beneficiary(
    session: AsyncSession, annuitant: Member, member: Member
):
    # Create a beneficiary on `member`, not `annuitant`
    from app.models.beneficiary import Beneficiary
    b = Beneficiary(
        member_id=member.id,
        beneficiary_type="individual",
        first_name="Other",
        last_name="Person",
        relationship="child",
        is_primary=True,
        effective_date=date(2020, 1, 1),
    )
    session.add(b)
    await session.flush()

    with pytest.raises(ValueError, match="not found on member"):
        await survivor_service.record_election(
            member_id=annuitant.id,
            option_type="js_50",
            member_monthly_annuity=Decimal("1900.00"),
            effective_date=date(2025, 1, 1),
            session=session,
            beneficiary_id=b.id,
        )


# ---------------------------------------------------------------------------
# get_current_election
# ---------------------------------------------------------------------------

async def test_get_current_election_returns_latest(session: AsyncSession, annuitant: Member, beneficiary: Beneficiary):
    await survivor_service.record_election(
        member_id=annuitant.id,
        option_type="single_life",
        member_monthly_annuity=Decimal("2000.00"),
        effective_date=date(2020, 1, 1),
        session=session,
    )
    await survivor_service.record_election(
        member_id=annuitant.id,
        option_type="js_50",
        member_monthly_annuity=Decimal("1900.00"),
        effective_date=date(2025, 1, 1),
        session=session,
        beneficiary_id=beneficiary.id,
        beneficiary_age_at_election=62,
    )

    election = await survivor_service.get_current_election(
        annuitant.id, session, as_of=date(2025, 6, 1)
    )
    assert election is not None
    assert election.option_type == "js_50"


async def test_get_current_election_respects_as_of(session: AsyncSession, annuitant: Member):
    await survivor_service.record_election(
        member_id=annuitant.id,
        option_type="single_life",
        member_monthly_annuity=Decimal("2000.00"),
        effective_date=date(2020, 1, 1),
        session=session,
    )
    # Asking for a date before the election exists
    election = await survivor_service.get_current_election(
        annuitant.id, session, as_of=date(2019, 12, 31)
    )
    assert election is None


async def test_get_current_election_none_when_no_elections(session: AsyncSession, annuitant: Member):
    result = await survivor_service.get_current_election(annuitant.id, session)
    assert result is None


# ---------------------------------------------------------------------------
# calculate_survivor_benefit
# ---------------------------------------------------------------------------

async def test_pre_retirement_death_returns_lump_sum(
    session: AsyncSession, member_with_contributions: Member
):
    result = await survivor_service.calculate_survivor_benefit(
        member_id=member_with_contributions.id,
        event_date=date(2025, 3, 1),
        session=session,
    )
    assert result.is_pre_retirement is True
    assert result.scenario == "pre_retirement_lump_sum"
    # 10 years × $4,000 = $40,000
    assert result.lump_sum_amount == Decimal("40000.00")


async def test_post_retirement_single_life_returns_no_benefit(
    session: AsyncSession, annuitant: Member
):
    await survivor_service.record_election(
        member_id=annuitant.id,
        option_type="single_life",
        member_monthly_annuity=Decimal("2000.00"),
        effective_date=date(2020, 1, 1),
        session=session,
    )
    result = await survivor_service.calculate_survivor_benefit(
        member_id=annuitant.id,
        event_date=date(2025, 3, 1),
        session=session,
    )
    assert result.scenario == "no_survivor_benefit"
    assert result.survivor_monthly_amount == Decimal("0")


async def test_post_retirement_js_50_survivor_amount(
    session: AsyncSession, annuitant: Member, beneficiary: Beneficiary
):
    await survivor_service.record_election(
        member_id=annuitant.id,
        option_type="js_50",
        member_monthly_annuity=Decimal("2000.00"),
        effective_date=date(2020, 1, 1),
        session=session,
        beneficiary_id=beneficiary.id,
        beneficiary_age_at_election=62,
    )
    result = await survivor_service.calculate_survivor_benefit(
        member_id=annuitant.id,
        event_date=date(2025, 3, 1),
        session=session,
    )
    assert result.scenario == "joint_and_survivor"
    assert result.survivor_monthly_amount == Decimal("1000.00")  # 50% of 2000
    assert result.beneficiary_id == beneficiary.id


async def test_post_retirement_js_75_survivor_amount(
    session: AsyncSession, annuitant: Member, beneficiary: Beneficiary
):
    await survivor_service.record_election(
        member_id=annuitant.id,
        option_type="js_75",
        member_monthly_annuity=Decimal("2000.00"),
        effective_date=date(2020, 1, 1),
        session=session,
        beneficiary_id=beneficiary.id,
        beneficiary_age_at_election=62,
    )
    result = await survivor_service.calculate_survivor_benefit(
        member_id=annuitant.id,
        event_date=date(2025, 3, 1),
        session=session,
    )
    assert result.survivor_monthly_amount == Decimal("1500.00")  # 75% of 2000


async def test_post_retirement_reversionary(
    session: AsyncSession, annuitant: Member, beneficiary: Beneficiary
):
    await survivor_service.record_election(
        member_id=annuitant.id,
        option_type="reversionary",
        member_monthly_annuity=Decimal("1800.00"),
        effective_date=date(2020, 1, 1),
        session=session,
        beneficiary_id=beneficiary.id,
        reversionary_monthly_amount=Decimal("600.00"),
    )
    result = await survivor_service.calculate_survivor_benefit(
        member_id=annuitant.id,
        event_date=date(2025, 3, 1),
        session=session,
    )
    assert result.scenario == "reversionary_annuity"
    assert result.survivor_monthly_amount == Decimal("600.00")


async def test_post_retirement_no_election_treated_as_no_benefit(
    session: AsyncSession, annuitant: Member
):
    # annuitant with no election on file
    result = await survivor_service.calculate_survivor_benefit(
        member_id=annuitant.id,
        event_date=date(2025, 3, 1),
        session=session,
    )
    assert result.scenario == "no_survivor_benefit"


# ---------------------------------------------------------------------------
# initiate_survivor_payments
# ---------------------------------------------------------------------------

async def test_initiate_payments_pre_retirement(
    session: AsyncSession, member_with_contributions: Member
):
    payments = await survivor_service.initiate_survivor_payments(
        member_id=member_with_contributions.id,
        event_date=date(2025, 3, 1),
        session=session,
    )
    assert len(payments) == 1
    assert payments[0].payment_type == "death_benefit"
    assert payments[0].gross_amount == Decimal("40000.00")
    assert payments[0].beneficiary_id is None


async def test_initiate_payments_single_life_creates_no_payments(
    session: AsyncSession, annuitant: Member
):
    await survivor_service.record_election(
        member_id=annuitant.id,
        option_type="single_life",
        member_monthly_annuity=Decimal("2000.00"),
        effective_date=date(2020, 1, 1),
        session=session,
    )
    payments = await survivor_service.initiate_survivor_payments(
        member_id=annuitant.id,
        event_date=date(2025, 3, 1),
        session=session,
    )
    assert payments == []


async def test_initiate_payments_survivor_annuity_routes_to_bene(
    session: AsyncSession, annuitant: Member, beneficiary: Beneficiary, bene_bank_account: BeneficiaryBankAccount
):
    await survivor_service.record_election(
        member_id=annuitant.id,
        option_type="js_100",
        member_monthly_annuity=Decimal("2000.00"),
        effective_date=date(2020, 1, 1),
        session=session,
        beneficiary_id=beneficiary.id,
        beneficiary_age_at_election=62,
    )
    payments = await survivor_service.initiate_survivor_payments(
        member_id=annuitant.id,
        event_date=date(2025, 3, 1),
        session=session,
    )
    assert len(payments) == 1
    p = payments[0]
    assert p.payment_type == "survivor_annuity"
    assert p.gross_amount == Decimal("2000.00")  # 100% of annuity
    assert p.beneficiary_id == beneficiary.id
    assert p.beneficiary_bank_account_id == bene_bank_account.id
    assert p.status == "pending"

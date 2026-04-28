"""Tests for beneficiary management service."""

from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.beneficiary import Beneficiary
from app.models.member import Member
from app.services import beneficiary_service

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def member(session: AsyncSession) -> Member:
    from app.crypto import encrypt_ssn
    m = Member(
        member_number="B001",
        first_name="Jane",
        last_name="Smith",
        date_of_birth=date(1965, 3, 15),
        ssn_encrypted=encrypt_ssn("123-45-6789"),
        ssn_last_four="6789",
    )
    session.add(m)
    await session.flush()
    return m


@pytest_asyncio.fixture
async def linked_member(session: AsyncSession) -> Member:
    from app.crypto import encrypt_ssn
    m = Member(
        member_number="B002",
        first_name="Robert",
        last_name="Smith",
        date_of_birth=date(1963, 7, 4),
        ssn_encrypted=encrypt_ssn("987-65-4321"),
        ssn_last_four="4321",
    )
    session.add(m)
    await session.flush()
    return m


@pytest_asyncio.fixture
async def individual_bene(session: AsyncSession, member: Member) -> Beneficiary:
    # No session.begin() — member fixture already autobegun the transaction
    return await beneficiary_service.add_beneficiary(
        member_id=member.id,
        beneficiary_type="individual",
        relationship="spouse",
        effective_date=date(2020, 1, 1),
        first_name="Robert",
        last_name="Smith",
        is_primary=True,
        session=session,
    )


# ---------------------------------------------------------------------------
# Unit tests (no DB — validate early guards before any session.get call)
# ---------------------------------------------------------------------------

async def test_invalid_type_raises():
    from unittest.mock import AsyncMock, MagicMock

    mock_session = MagicMock()
    mock_session.get = AsyncMock(return_value=MagicMock())

    with pytest.raises(ValueError, match="Invalid beneficiary_type"):
        await beneficiary_service.add_beneficiary(
            member_id=None,
            beneficiary_type="bogus",
            relationship="friend",
            effective_date=date(2020, 1, 1),
            session=mock_session,
        )


async def test_valid_individual_requires_names():
    from unittest.mock import AsyncMock, MagicMock

    mock_session = MagicMock()
    mock_session.get = AsyncMock(return_value=MagicMock())

    with pytest.raises(ValueError, match="first_name and last_name"):
        await beneficiary_service.add_beneficiary(
            member_id=None,
            beneficiary_type="individual",
            relationship="spouse",
            effective_date=date(2020, 1, 1),
            first_name=None,
            last_name=None,
            session=mock_session,
        )


async def test_estate_requires_org_name():
    from unittest.mock import AsyncMock, MagicMock

    mock_session = MagicMock()
    mock_session.get = AsyncMock(return_value=MagicMock())

    with pytest.raises(ValueError, match="org_name is required"):
        await beneficiary_service.add_beneficiary(
            member_id=None,
            beneficiary_type="estate",
            relationship="estate",
            effective_date=date(2020, 1, 1),
            org_name=None,
            session=mock_session,
        )


# ---------------------------------------------------------------------------
# DB tests — no explicit session.begin(); fixtures autobegun the transaction
# ---------------------------------------------------------------------------

async def test_add_individual_beneficiary(session: AsyncSession, member: Member):
    bene = await beneficiary_service.add_beneficiary(
        member_id=member.id,
        beneficiary_type="individual",
        relationship="spouse",
        effective_date=date(2020, 1, 1),
        first_name="Robert",
        last_name="Smith",
        date_of_birth=date(1963, 7, 4),
        is_primary=True,
        share_percent=100.0,
        session=session,
    )

    assert bene.id is not None
    assert bene.beneficiary_type == "individual"
    assert bene.first_name == "Robert"
    assert bene.org_name is None
    assert bene.is_primary is True
    assert bene.share_percent == 100.0


async def test_add_estate_beneficiary(session: AsyncSession, member: Member):
    bene = await beneficiary_service.add_beneficiary(
        member_id=member.id,
        beneficiary_type="estate",
        relationship="estate",
        effective_date=date(2020, 1, 1),
        org_name="Estate of Jane Smith",
        is_primary=False,
        session=session,
    )

    assert bene.beneficiary_type == "estate"
    assert bene.org_name == "Estate of Jane Smith"
    assert bene.first_name is None
    assert bene.last_name is None


async def test_add_trust_beneficiary(session: AsyncSession, member: Member):
    bene = await beneficiary_service.add_beneficiary(
        member_id=member.id,
        beneficiary_type="trust",
        relationship="trust",
        effective_date=date(2020, 1, 1),
        org_name="Smith Family Trust",
        session=session,
    )

    assert bene.beneficiary_type == "trust"
    assert bene.org_name == "Smith Family Trust"


async def test_add_beneficiary_with_ssn(session: AsyncSession, member: Member):
    bene = await beneficiary_service.add_beneficiary(
        member_id=member.id,
        beneficiary_type="individual",
        relationship="spouse",
        effective_date=date(2020, 1, 1),
        first_name="Robert",
        last_name="Smith",
        ssn="987-65-4321",
        session=session,
    )

    assert bene.ssn_last_four == "4321"
    assert bene.ssn_encrypted is not None
    assert bene.ssn_encrypted != b"987-65-4321"


async def test_add_beneficiary_with_linked_member(
    session: AsyncSession, member: Member, linked_member: Member
):
    bene = await beneficiary_service.add_beneficiary(
        member_id=member.id,
        beneficiary_type="individual",
        relationship="spouse",
        effective_date=date(2020, 1, 1),
        first_name="Robert",
        last_name="Smith",
        linked_member_id=linked_member.id,
        session=session,
    )

    assert bene.linked_member_id == linked_member.id


async def test_add_beneficiary_member_not_found(session: AsyncSession):
    import uuid
    with pytest.raises(ValueError, match="not found"):
        await beneficiary_service.add_beneficiary(
            member_id=uuid.uuid4(),
            beneficiary_type="individual",
            relationship="spouse",
            effective_date=date(2020, 1, 1),
            first_name="Robert",
            last_name="Smith",
            session=session,
        )


async def test_add_beneficiary_linked_member_not_found(session: AsyncSession, member: Member):
    import uuid
    with pytest.raises(ValueError, match="Linked member"):
        await beneficiary_service.add_beneficiary(
            member_id=member.id,
            beneficiary_type="individual",
            relationship="spouse",
            effective_date=date(2020, 1, 1),
            first_name="Robert",
            last_name="Smith",
            linked_member_id=uuid.uuid4(),
            session=session,
        )


async def test_list_beneficiaries_all(session: AsyncSession, member: Member):
    await beneficiary_service.add_beneficiary(
        member_id=member.id, beneficiary_type="individual", relationship="spouse",
        effective_date=date(2020, 1, 1), first_name="Robert", last_name="Smith",
        is_primary=True, session=session,
    )
    await beneficiary_service.add_beneficiary(
        member_id=member.id, beneficiary_type="individual", relationship="child",
        effective_date=date(2020, 1, 1), first_name="Alice", last_name="Smith",
        is_primary=False, session=session,
    )

    results = await beneficiary_service.list_beneficiaries(member.id, session)
    assert len(results) == 2


async def test_list_beneficiaries_primary_filter(session: AsyncSession, member: Member):
    await beneficiary_service.add_beneficiary(
        member_id=member.id, beneficiary_type="individual", relationship="spouse",
        effective_date=date(2020, 1, 1), first_name="Robert", last_name="Smith",
        is_primary=True, session=session,
    )
    await beneficiary_service.add_beneficiary(
        member_id=member.id, beneficiary_type="individual", relationship="child",
        effective_date=date(2020, 1, 1), first_name="Alice", last_name="Smith",
        is_primary=False, session=session,
    )

    primary = await beneficiary_service.list_beneficiaries(member.id, session, is_primary=True)
    contingent = await beneficiary_service.list_beneficiaries(member.id, session, is_primary=False)
    assert len(primary) == 1
    assert len(contingent) == 1
    assert primary[0].first_name == "Robert"


async def test_list_beneficiaries_active_only(session: AsyncSession, member: Member):
    await beneficiary_service.add_beneficiary(
        member_id=member.id, beneficiary_type="individual", relationship="spouse",
        effective_date=date(2020, 1, 1), first_name="Robert", last_name="Smith",
        session=session,
    )
    await beneficiary_service.add_beneficiary(
        member_id=member.id, beneficiary_type="individual", relationship="child",
        effective_date=date(2020, 1, 1), first_name="Alice", last_name="Smith",
        end_date=date(2022, 12, 31), session=session,
    )

    active = await beneficiary_service.list_beneficiaries(member.id, session, active_only=True)
    assert len(active) == 1
    assert active[0].first_name == "Robert"


async def test_get_beneficiary(session: AsyncSession, individual_bene: Beneficiary):
    result = await beneficiary_service.get_beneficiary(individual_bene.id, session)
    assert result is not None
    assert result.id == individual_bene.id


async def test_get_beneficiary_not_found(session: AsyncSession):
    import uuid
    result = await beneficiary_service.get_beneficiary(uuid.uuid4(), session)
    assert result is None


async def test_close_beneficiary(session: AsyncSession, member: Member, individual_bene: Beneficiary):
    closed = await beneficiary_service.close_beneficiary(
        individual_bene.id, member.id, date(2024, 12, 31), session
    )

    assert closed.end_date == date(2024, 12, 31)


async def test_close_already_closed_raises(session: AsyncSession, member: Member, individual_bene: Beneficiary):
    await beneficiary_service.close_beneficiary(
        individual_bene.id, member.id, date(2024, 12, 31), session
    )

    with pytest.raises(ValueError, match="already closed"):
        await beneficiary_service.close_beneficiary(
            individual_bene.id, member.id, date(2025, 1, 1), session
        )


async def test_close_wrong_member_raises(session: AsyncSession, individual_bene: Beneficiary, linked_member: Member):
    with pytest.raises(ValueError, match="not found for this member"):
        await beneficiary_service.close_beneficiary(
            individual_bene.id, linked_member.id, date(2024, 12, 31), session
        )


# ---------------------------------------------------------------------------
# Bank account tests
# ---------------------------------------------------------------------------

async def test_add_bank_account(session: AsyncSession, individual_bene: Beneficiary):
    acct = await beneficiary_service.add_bank_account(
        individual_bene.id,
        bank_name="First National",
        routing_number="123456789",
        account_number="999888777",
        account_last_four="8777",
        account_type="checking",
        effective_date=date(2024, 1, 1),
        is_primary=True,
        session=session,
    )

    assert acct.id is not None
    assert acct.account_last_four == "8777"
    assert acct.account_number_encrypted != b"999888777"
    assert acct.is_primary is True


async def test_bank_account_beneficiary_not_found(session: AsyncSession):
    import uuid
    with pytest.raises(ValueError, match="not found"):
        await beneficiary_service.add_bank_account(
            uuid.uuid4(),
            bank_name="First National",
            routing_number="123456789",
            account_number="999888777",
            account_last_four="8777",
            account_type="checking",
            effective_date=date(2024, 1, 1),
            session=session,
        )

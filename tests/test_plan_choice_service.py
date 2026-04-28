"""Tests for plan choice service."""

from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.member import Member
from app.models.plan_config import PlanTier, PlanType
from app.services import plan_choice_service

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def member(session: AsyncSession) -> Member:
    from app.crypto import encrypt_ssn
    m = Member(
        member_number="PC001",
        first_name="Jane",
        last_name="Smith",
        date_of_birth=date(1965, 3, 15),
        ssn_encrypted=encrypt_ssn("111-22-3333"),
        ssn_last_four="3333",
    )
    session.add(m)
    await session.flush()
    return m


@pytest_asyncio.fixture
async def tier(session: AsyncSession) -> PlanTier:
    t = PlanTier(
        tier_code="TIER_I",
        tier_label="Tier I",
        effective_date=date(2000, 1, 1),
    )
    session.add(t)
    await session.flush()
    return t


@pytest_asyncio.fixture
async def plan_type(session: AsyncSession) -> PlanType:
    p = PlanType(
        plan_code="TRADITIONAL",
        plan_label="Traditional",
    )
    session.add(p)
    await session.flush()
    return p


# ---------------------------------------------------------------------------
# set_plan_choice
# ---------------------------------------------------------------------------

async def test_set_plan_choice(session: AsyncSession, member: Member, tier: PlanTier, plan_type: PlanType):
    updated = await plan_choice_service.set_plan_choice(
        member.id, tier.id, plan_type.id, date(2024, 9, 1), session
    )

    assert updated.plan_tier_id == tier.id
    assert updated.plan_type_id == plan_type.id
    assert updated.plan_choice_date == date(2024, 9, 1)
    assert updated.plan_choice_locked is False


async def test_set_plan_choice_member_not_found(session: AsyncSession, tier: PlanTier, plan_type: PlanType):
    import uuid
    with pytest.raises(ValueError, match="not found"):
        await plan_choice_service.set_plan_choice(
            uuid.uuid4(), tier.id, plan_type.id, date(2024, 9, 1), session
        )


async def test_set_plan_choice_invalid_tier(session: AsyncSession, member: Member, plan_type: PlanType):
    import uuid
    with pytest.raises(ValueError, match="Plan tier"):
        await plan_choice_service.set_plan_choice(
            member.id, uuid.uuid4(), plan_type.id, date(2024, 9, 1), session
        )


async def test_set_plan_choice_invalid_type(session: AsyncSession, member: Member, tier: PlanTier):
    import uuid
    with pytest.raises(ValueError, match="Plan type"):
        await plan_choice_service.set_plan_choice(
            member.id, tier.id, uuid.uuid4(), date(2024, 9, 1), session
        )


async def test_set_plan_choice_locked_raises(
    session: AsyncSession, member: Member, tier: PlanTier, plan_type: PlanType
):
    await plan_choice_service.set_plan_choice(
        member.id, tier.id, plan_type.id, date(2024, 9, 1), session
    )
    await plan_choice_service.lock_plan_choice(member.id, session)

    with pytest.raises(ValueError, match="locked"):
        await plan_choice_service.set_plan_choice(
            member.id, tier.id, plan_type.id, date(2024, 10, 1), session
        )


async def test_set_plan_choice_can_change_before_lock(
    session: AsyncSession, member: Member, tier: PlanTier, plan_type: PlanType
):
    await plan_choice_service.set_plan_choice(
        member.id, tier.id, plan_type.id, date(2024, 9, 1), session
    )

    tier2 = PlanTier(
        tier_code="TIER_II",
        tier_label="Tier II",
        effective_date=date(2011, 1, 1),
    )
    session.add(tier2)
    await session.flush()

    updated = await plan_choice_service.set_plan_choice(
        member.id, tier2.id, plan_type.id, date(2024, 9, 15), session
    )

    assert updated.plan_tier_id == tier2.id


# ---------------------------------------------------------------------------
# lock_plan_choice
# ---------------------------------------------------------------------------

async def test_lock_plan_choice(
    session: AsyncSession, member: Member, tier: PlanTier, plan_type: PlanType
):
    await plan_choice_service.set_plan_choice(
        member.id, tier.id, plan_type.id, date(2024, 9, 1), session
    )

    locked = await plan_choice_service.lock_plan_choice(member.id, session)

    assert locked.plan_choice_locked is True


async def test_lock_without_selection_raises(session: AsyncSession, member: Member):
    with pytest.raises(ValueError, match="no plan has been selected"):
        await plan_choice_service.lock_plan_choice(member.id, session)


async def test_lock_already_locked_raises(
    session: AsyncSession, member: Member, tier: PlanTier, plan_type: PlanType
):
    await plan_choice_service.set_plan_choice(
        member.id, tier.id, plan_type.id, date(2024, 9, 1), session
    )
    await plan_choice_service.lock_plan_choice(member.id, session)

    with pytest.raises(ValueError, match="already locked"):
        await plan_choice_service.lock_plan_choice(member.id, session)


async def test_lock_member_not_found(session: AsyncSession):
    import uuid
    with pytest.raises(ValueError, match="not found"):
        await plan_choice_service.lock_plan_choice(uuid.uuid4(), session)

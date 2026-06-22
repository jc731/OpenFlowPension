"""Tests for survivor annuity termination (US-S08)."""

from datetime import date

import pytest

from app.crypto import encrypt_ssn
from app.models.beneficiary import Beneficiary
from app.models.member import Member
from app.models.payment import BenefitPayment
from app.models.plan_config import PlanTier, PlanType
from app.services.survivor_service import terminate_survivor_annuity


async def _make_member(session) -> Member:
    tier = PlanTier(tier_code="tier_1", tier_label="Tier I", effective_date=date(1980, 1, 1))
    plan = PlanType(plan_code="traditional", plan_label="Traditional")
    session.add_all([tier, plan])
    await session.flush()
    member = Member(
        member_number="ST-001",
        first_name="Jane",
        last_name="Smith",
        date_of_birth=date(1950, 1, 1),
        ssn_encrypted=encrypt_ssn("123456789"),
        ssn_last_four="6789",
        certification_date=date(1990, 1, 1),
        plan_tier_id=tier.id,
        plan_type_id=plan.id,
        member_status="annuitant",
    )
    session.add(member)
    await session.flush()
    return member


async def _make_beneficiary(session, member_id) -> Beneficiary:
    bene = Beneficiary(
        member_id=member_id,
        beneficiary_type="individual",
        first_name="Bob",
        last_name="Smith",
        relationship="spouse",
        is_primary=True,
        effective_date=date(2000, 1, 1),
    )
    session.add(bene)
    await session.flush()
    return bene


async def _make_survivor_payment(session, member_id, beneficiary_id, status="pending") -> BenefitPayment:
    p = BenefitPayment(
        member_id=member_id,
        beneficiary_id=beneficiary_id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        payment_date=date(2026, 1, 31),
        gross_amount=1200.0,
        net_amount=1200.0,
        payment_type="survivor_annuity",
        payment_method="ach",
        status=status,
    )
    session.add(p)
    await session.flush()
    return p


async def test_terminate_sets_deceased_date(session):
    async with session.begin():
        member = await _make_member(session)
        bene = await _make_beneficiary(session, member.id)
        result = await terminate_survivor_annuity(bene.id, date(2026, 3, 15), session)

    assert result.deceased_date == date(2026, 3, 15)
    assert result.end_date == date(2026, 3, 15)


async def test_terminate_cancels_pending_payments(session):
    async with session.begin():
        member = await _make_member(session)
        bene = await _make_beneficiary(session, member.id)
        p = await _make_survivor_payment(session, member.id, bene.id, status="pending")
        await terminate_survivor_annuity(bene.id, date(2026, 3, 15), session)
        await session.refresh(p)

    assert p.status == "cancelled"


async def test_terminate_leaves_issued_payments_alone(session):
    async with session.begin():
        member = await _make_member(session)
        bene = await _make_beneficiary(session, member.id)
        p = await _make_survivor_payment(session, member.id, bene.id, status="issued")
        await terminate_survivor_annuity(bene.id, date(2026, 3, 15), session)
        await session.refresh(p)

    assert p.status == "issued"  # already disbursed — untouched


async def test_terminate_already_deceased_raises(session):
    async with session.begin():
        member = await _make_member(session)
        bene = await _make_beneficiary(session, member.id)
        await terminate_survivor_annuity(bene.id, date(2026, 3, 15), session)
        with pytest.raises(ValueError, match="already recorded as deceased"):
            await terminate_survivor_annuity(bene.id, date(2026, 4, 1), session)


async def test_terminate_not_found_raises(session):
    import uuid
    with pytest.raises(ValueError, match="Beneficiary not found"):
        async with session.begin():
            await terminate_survivor_annuity(uuid.uuid4(), date(2026, 3, 15), session)

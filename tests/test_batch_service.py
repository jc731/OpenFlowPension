"""Tests for payment batch service and payment reversal."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio

from app.crypto import encrypt_ssn
from app.models.member import Member
from app.models.payment import BenefitPayment, PaymentBatch
from app.models.plan_config import PlanTier, PlanType
from app.services import batch_service
from app.services.payment_service import reverse_payment


# ── Fixtures ──────────────────────────────────────────────────────────────────

async def _make_member(session) -> Member:
    tier = PlanTier(tier_code="tier_1", tier_label="Tier I", effective_date=date(1980, 1, 1))
    plan = PlanType(plan_code="traditional", plan_label="Traditional")
    session.add_all([tier, plan])
    await session.flush()
    member = Member(
        member_number="B-001",
        first_name="Jane",
        last_name="Smith",
        date_of_birth=date(1955, 1, 1),
        ssn_encrypted=encrypt_ssn("999887777"),
        ssn_last_four="7777",
        certification_date=date(2000, 1, 1),
        plan_tier_id=tier.id,
        plan_type_id=plan.id,
    )
    session.add(member)
    await session.flush()
    return member


async def _make_payment(session, member_id, gross=3000.0) -> BenefitPayment:
    payment = BenefitPayment(
        member_id=member_id,
        period_start=date(2025, 1, 1),
        period_end=date(2025, 1, 31),
        payment_date=date(2025, 1, 31),
        gross_amount=gross,
        net_amount=gross,
        payment_type="annuity",
        payment_method="ach",
        status="pending",
    )
    session.add(payment)
    await session.flush()
    return payment


# ── create_batch ──────────────────────────────────────────────────────────────

async def test_create_batch_creates_draft(session):
    async with session.begin():
        member = await _make_member(session)
        p1 = await _make_payment(session, member.id, gross=3000.0)
        p2 = await _make_payment(session, member.id, gross=1500.0)
        batch = await batch_service.create_batch(
            [p1.id, p2.id],
            date(2025, 1, 31),
            "annuity",
            session,
        )

    assert batch.status == "draft"
    assert batch.payment_type == "annuity"
    assert batch.batch_date == date(2025, 1, 31)
    assert batch.total_gross is None
    assert batch.total_net is None


async def test_create_batch_links_payments(session):
    async with session.begin():
        member = await _make_member(session)
        p = await _make_payment(session, member.id)
        batch = await batch_service.create_batch([p.id], date(2025, 1, 31), "annuity", session)
        await session.refresh(p)

    assert p.batch_id == batch.id


async def test_create_batch_empty_raises(session):
    with pytest.raises(ValueError, match="payment_ids must not be empty"):
        async with session.begin():
            await batch_service.create_batch([], date(2025, 1, 31), "annuity", session)


async def test_create_batch_missing_payment_raises(session):
    import uuid
    with pytest.raises(ValueError, match="Payments not found"):
        async with session.begin():
            await batch_service.create_batch(
                [uuid.uuid4()], date(2025, 1, 31), "annuity", session
            )


async def test_create_batch_already_batched_raises(session):
    async with session.begin():
        member = await _make_member(session)
        p = await _make_payment(session, member.id)
        await batch_service.create_batch([p.id], date(2025, 1, 31), "annuity", session)
    with pytest.raises(ValueError, match="already assigned to a batch"):
        async with session.begin():
            await batch_service.create_batch([p.id], date(2025, 1, 31), "annuity", session)


async def test_create_batch_non_pending_raises(session):
    async with session.begin():
        member = await _make_member(session)
        p = await _make_payment(session, member.id)
        p.status = "issued"

    with pytest.raises(ValueError, match="Only pending payments"):
        async with session.begin():
            await batch_service.create_batch([p.id], date(2025, 1, 31), "annuity", session)


# ── dispatch_batch ────────────────────────────────────────────────────────────

async def _batch_in_net_pay_applied_state(session, member) -> PaymentBatch:
    """Create a batch manually set to net_pay_applied, bypassing the actual net pay engine."""
    p1 = await _make_payment(session, member.id, gross=2000.0)
    p2 = await _make_payment(session, member.id, gross=1000.0)
    batch = await batch_service.create_batch(
        [p1.id, p2.id], date(2025, 1, 31), "annuity", session
    )
    batch.status = "net_pay_applied"
    batch.total_gross = 3000.0
    batch.total_net = 2700.0
    batch.payment_count = 2
    await session.flush()
    return batch


async def test_dispatch_batch_json_returns_payload(session):
    async with session.begin():
        member = await _make_member(session)
        batch = await _batch_in_net_pay_applied_state(session, member)
        payload = await batch_service.dispatch_batch(batch.id, "json", session)

    assert payload["batch_id"] == str(batch.id)
    assert payload["payment_type"] == "annuity"
    assert len(payload["payments"]) == 2


async def test_dispatch_batch_sets_dispatched_status(session):
    async with session.begin():
        member = await _make_member(session)
        batch = await _batch_in_net_pay_applied_state(session, member)
        await batch_service.dispatch_batch(batch.id, "json", session)
        await session.refresh(batch)

    assert batch.status == "dispatched"
    assert batch.dispatch_format == "json"
    assert batch.dispatched_at is not None


async def test_dispatch_batch_nacha_raises_not_implemented(session):
    async with session.begin():
        member = await _make_member(session)
        batch = await _batch_in_net_pay_applied_state(session, member)
        with pytest.raises(NotImplementedError):
            await batch_service.dispatch_batch(batch.id, "nacha", session)


async def test_dispatch_wrong_status_raises(session):
    async with session.begin():
        member = await _make_member(session)
        p = await _make_payment(session, member.id)
        batch = await batch_service.create_batch([p.id], date(2025, 1, 31), "annuity", session)
        with pytest.raises(ValueError, match="Cannot dispatch"):
            await batch_service.dispatch_batch(batch.id, "json", session)


# ── reconcile_batch ───────────────────────────────────────────────────────────

async def test_reconcile_batch_marks_payments_issued(session):
    async with session.begin():
        member = await _make_member(session)
        batch = await _batch_in_net_pay_applied_state(session, member)
        await batch_service.dispatch_batch(batch.id, "json", session)
        batch_id = batch.id

    async with session.begin():
        await batch_service.reconcile_batch(batch_id, session)

    from sqlalchemy import select
    from app.models.payment import BenefitPayment as BP
    result = await session.execute(select(BP).where(BP.batch_id == batch_id))
    payments = result.scalars().all()
    assert all(p.status == "issued" for p in payments)


async def test_reconcile_batch_sets_reconciled_status(session):
    async with session.begin():
        member = await _make_member(session)
        batch = await _batch_in_net_pay_applied_state(session, member)
        await batch_service.dispatch_batch(batch.id, "json", session)
        batch_id = batch.id

    async with session.begin():
        reconciled = await batch_service.reconcile_batch(batch_id, session)

    assert reconciled.status == "reconciled"
    assert reconciled.reconciled_at is not None


async def test_reconcile_wrong_status_raises(session):
    async with session.begin():
        member = await _make_member(session)
        batch = await _batch_in_net_pay_applied_state(session, member)
        with pytest.raises(ValueError, match="Cannot reconcile"):
            await batch_service.reconcile_batch(batch.id, session)


# ── reverse_payment ───────────────────────────────────────────────────────────

async def test_reverse_payment_sets_reversed(session):
    async with session.begin():
        member = await _make_member(session)
        p = await _make_payment(session, member.id)
        reversed_p = await reverse_payment(p.id, "Duplicate disbursement", session)

    assert reversed_p.status == "reversed"
    assert reversed_p.note == "Duplicate disbursement"


async def test_reverse_payment_already_reversed_raises(session):
    async with session.begin():
        member = await _make_member(session)
        p = await _make_payment(session, member.id)
        await reverse_payment(p.id, "Error", session)
        with pytest.raises(ValueError, match="already reversed"):
            await reverse_payment(p.id, "Again", session)


async def test_reverse_payment_cancelled_raises(session):
    async with session.begin():
        member = await _make_member(session)
        p = await _make_payment(session, member.id)
        p.status = "cancelled"
        with pytest.raises(ValueError, match="Cannot reverse a cancelled"):
            await reverse_payment(p.id, "Oops", session)

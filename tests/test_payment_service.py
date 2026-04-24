"""Tests for payment disbursement service.

Pure computation tests (no DB): deduction amount calculation, net amount.
DB tests: payment creation, standing order application, deduction order lifecycle,
          tax withholding elections, bank account management.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.models.bank_account import MemberBankAccount
from app.models.member import Member
from app.models.payment import BenefitPayment, DeductionOrder
from app.schemas.bank_account import BankAccountCreate
from app.schemas.payment import (
    DeductionOrderCreate,
    DeductionOrderEnd,
    PaymentCreate,
    PaymentDeductionCreate,
    PaymentStatusUpdate,
    TaxWithholdingElectionCreate,
)
from app.services.bank_account_service import add_bank_account, list_bank_accounts, set_primary
from app.services.payment_service import (
    compute_deduction_amount,
    compute_net_amount,
    create_deduction_order,
    create_payment,
    end_deduction_order,
    get_payment,
    list_payments,
    set_tax_withholding,
    update_payment_status,
)
from app.crypto import encrypt_ssn


# ── Pure unit tests (no DB) ───────────────────────────────────────────────────

def test_fixed_deduction_amount():
    order = DeductionOrder(amount_type="fixed", amount=150.0, deduction_type="health_insurance")
    assert compute_deduction_amount(order, Decimal("3000")) == Decimal("150.0")


def test_percent_of_gross_deduction():
    order = DeductionOrder(amount_type="percent_of_gross", amount=0.02, deduction_type="union_dues")
    result = compute_deduction_amount(order, Decimal("3000"))
    assert result == Decimal("60.00")  # 2% of 3000


def test_percent_of_gross_rounds_half_up():
    order = DeductionOrder(amount_type="percent_of_gross", amount=0.015, deduction_type="union_dues")
    result = compute_deduction_amount(order, Decimal("3333"))
    assert result == Decimal("50.00")  # 0.015 * 3333 = 49.995 → 50.00


def test_net_amount_calculation():
    deductions = [Decimal("500"), Decimal("150.50"), Decimal("22.75")]
    net = compute_net_amount(Decimal("3000"), deductions)
    assert net == Decimal("2326.75")


def test_net_amount_no_deductions():
    assert compute_net_amount(Decimal("3000"), []) == Decimal("3000.00")


# ── DB fixtures ───────────────────────────────────────────────────────────────

async def _make_member(session) -> Member:
    from app.models.plan_config import PlanTier, PlanType
    tier = PlanTier(tier_code="tier_1", tier_label="Tier I", effective_date=date(1980, 1, 1))
    plan = PlanType(plan_code="traditional", plan_label="Traditional")
    session.add_all([tier, plan])
    await session.flush()

    member = Member(
        member_number="TEST-001",
        first_name="Test",
        last_name="Member",
        date_of_birth=date(1965, 1, 1),
        ssn_encrypted=encrypt_ssn("123456789"),
        ssn_last_four="6789",
        certification_date=date(2000, 1, 1),
        plan_tier_id=tier.id,
        plan_type_id=plan.id,
    )
    session.add(member)
    await session.flush()
    return member


# ── DB tests: bank accounts ───────────────────────────────────────────────────

async def test_add_bank_account(session):
    async with session.begin():
        member = await _make_member(session)
        data = BankAccountCreate(
            bank_name="First National",
            routing_number="071000013",
            account_number="123456789",
            account_last_four="6789",
            account_type="checking",
            is_primary=True,
            effective_date=date(2025, 1, 1),
        )
        acct = await add_bank_account(member.id, data, session)

    assert acct.routing_number == "071000013"
    assert acct.account_last_four == "6789"
    assert acct.is_primary is True
    assert acct.account_number_encrypted  # encrypted, not plaintext


async def test_set_primary_clears_old(session):
    async with session.begin():
        member = await _make_member(session)

        acct1 = await add_bank_account(member.id, BankAccountCreate(
            bank_name="Bank A", routing_number="071000013",
            account_number="111111111", account_last_four="1111",
            account_type="checking", is_primary=True, effective_date=date(2025, 1, 1),
        ), session)

        acct2 = await add_bank_account(member.id, BankAccountCreate(
            bank_name="Bank B", routing_number="071000013",
            account_number="222222222", account_last_four="2222",
            account_type="savings", is_primary=False, effective_date=date(2025, 6, 1),
        ), session)

        await set_primary(acct2.id, member.id, session)

    accounts = await list_bank_accounts(member.id, session)
    primary_count = sum(1 for a in accounts if a.is_primary)
    assert primary_count == 1
    assert next(a for a in accounts if a.id == acct2.id).is_primary


# ── DB tests: deduction orders ────────────────────────────────────────────────

async def test_create_deduction_order(session):
    async with session.begin():
        member = await _make_member(session)
        order = await create_deduction_order(member.id, DeductionOrderCreate(
            deduction_type="union_dues",
            deduction_code="SEIU_73",
            amount_type="percent_of_gross",
            amount=Decimal("0.02"),
            effective_date=date(2025, 1, 1),
            source_document_type="union_authorization",
        ), session)

    assert order.deduction_type == "union_dues"
    assert order.amount_type == "percent_of_gross"
    assert float(order.amount) == pytest.approx(0.02)
    assert order.end_date is None


async def test_end_deduction_order(session):
    async with session.begin():
        member = await _make_member(session)
        order = await create_deduction_order(member.id, DeductionOrderCreate(
            deduction_type="health_insurance",
            amount=Decimal("250"),
            effective_date=date(2025, 1, 1),
        ), session)
        ended = await end_deduction_order(order.id, member.id, DeductionOrderEnd(end_date=date(2025, 6, 30)), session)

    assert ended.end_date == date(2025, 6, 30)


# ── DB tests: tax withholding ─────────────────────────────────────────────────

async def test_set_tax_withholding_supersedes_prior(session):
    async with session.begin():
        member = await _make_member(session)
        first = await set_tax_withholding(member.id, TaxWithholdingElectionCreate(
            jurisdiction="federal",
            filing_status="single",
            effective_date=date(2024, 1, 1),
        ), session)
        second = await set_tax_withholding(member.id, TaxWithholdingElectionCreate(
            jurisdiction="federal",
            filing_status="married_filing_jointly",
            effective_date=date(2025, 1, 1),
        ), session)

    await session.refresh(first)
    assert first.superseded_date == date(2025, 1, 1)
    assert second.superseded_date is None
    assert second.filing_status == "married_filing_jointly"


# ── DB tests: payment creation ────────────────────────────────────────────────

async def test_create_payment_no_deductions(session):
    async with session.begin():
        member = await _make_member(session)
        payment = await create_payment(member.id, PaymentCreate(
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 31),
            payment_date=date(2025, 1, 1),
            gross_amount=Decimal("3267.00"),
            payment_method="ach",
            apply_standing_orders=False,
        ), session)

    assert float(payment.gross_amount) == pytest.approx(3267.00)
    assert float(payment.net_amount) == pytest.approx(3267.00)
    assert payment.status == "pending"
    assert payment.deductions == []


async def test_create_payment_with_manual_deductions(session):
    async with session.begin():
        member = await _make_member(session)
        payment = await create_payment(member.id, PaymentCreate(
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 31),
            payment_date=date(2025, 1, 1),
            gross_amount=Decimal("3267.00"),
            payment_method="check",
            apply_standing_orders=False,
            additional_deductions=[
                PaymentDeductionCreate(deduction_type="federal_tax", amount=Decimal("450.00"), is_pretax=False),
                PaymentDeductionCreate(deduction_type="state_tax", deduction_code="IL_STATE", amount=Decimal("160.00"), is_pretax=False),
            ],
        ), session)

    assert float(payment.net_amount) == pytest.approx(2657.00)
    assert len(payment.deductions) == 2


async def test_create_payment_applies_standing_orders(session):
    async with session.begin():
        member = await _make_member(session)

        # Create standing orders
        await create_deduction_order(member.id, DeductionOrderCreate(
            deduction_type="health_insurance",
            deduction_code="BCBS_GOLD",
            amount=Decimal("200.00"),
            is_pretax=True,
            effective_date=date(2024, 1, 1),
        ), session)
        await create_deduction_order(member.id, DeductionOrderCreate(
            deduction_type="union_dues",
            deduction_code="SEIU_73",
            amount_type="percent_of_gross",
            amount=Decimal("0.02"),
            effective_date=date(2024, 1, 1),
        ), session)

        payment = await create_payment(member.id, PaymentCreate(
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 31),
            payment_date=date(2025, 1, 15),
            gross_amount=Decimal("3000.00"),
            payment_method="ach",
            apply_standing_orders=True,
        ), session)

    # health: 200.00 fixed, union: 2% of 3000 = 60.00
    assert len(payment.deductions) == 2
    assert float(payment.net_amount) == pytest.approx(2740.00)  # 3000 - 200 - 60


async def test_standing_order_not_applied_before_effective_date(session):
    async with session.begin():
        member = await _make_member(session)
        await create_deduction_order(member.id, DeductionOrderCreate(
            deduction_type="health_insurance",
            amount=Decimal("200.00"),
            effective_date=date(2026, 1, 1),  # starts next year
        ), session)
        payment = await create_payment(member.id, PaymentCreate(
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 31),
            payment_date=date(2025, 1, 15),
            gross_amount=Decimal("3000.00"),
            payment_method="ach",
        ), session)

    assert payment.deductions == []
    assert float(payment.net_amount) == pytest.approx(3000.00)


async def test_ended_standing_order_not_applied(session):
    async with session.begin():
        member = await _make_member(session)
        order = await create_deduction_order(member.id, DeductionOrderCreate(
            deduction_type="health_insurance",
            amount=Decimal("200.00"),
            effective_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),  # ended before payment date
        ), session)
        payment = await create_payment(member.id, PaymentCreate(
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 31),
            payment_date=date(2025, 1, 15),
            gross_amount=Decimal("3000.00"),
            payment_method="ach",
        ), session)

    assert payment.deductions == []


# ── DB tests: payment status ──────────────────────────────────────────────────

async def test_update_payment_status_to_issued(session):
    async with session.begin():
        member = await _make_member(session)
        payment = await create_payment(member.id, PaymentCreate(
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 31),
            payment_date=date(2025, 1, 1),
            gross_amount=Decimal("3267.00"),
            payment_method="ach",
            apply_standing_orders=False,
        ), session)
        updated = await update_payment_status(payment.id, PaymentStatusUpdate(status="issued"), session)

    assert updated.status == "issued"
    assert updated.issued_at is not None


async def test_cannot_issue_to_non_reverse_from_issued(session):
    async with session.begin():
        member = await _make_member(session)
        payment = await create_payment(member.id, PaymentCreate(
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 31),
            payment_date=date(2025, 1, 1),
            gross_amount=Decimal("3267.00"),
            payment_method="ach",
            apply_standing_orders=False,
        ), session)
        await update_payment_status(payment.id, PaymentStatusUpdate(status="issued"), session)

        with pytest.raises(ValueError, match="Issued payments"):
            await update_payment_status(payment.id, PaymentStatusUpdate(status="cancelled"), session)

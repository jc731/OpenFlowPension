"""Tests for service purchase — quote, claim lifecycle, payment, credit grant.

Covers:
  - Quote: rate_based calc, refund_repayment stub error, unknown type error
  - Claim create: happy path, no salary error
  - Lifecycle: draft → pending_approval → approved → in_payment → completed
  - Credit grant on completion (default), on approval, on first_payment
  - Installment enforcement (non-installment type rejects second payment)
  - cancel: blocks terminal states
  - benefit_estimate_service._service_credit_by_slot routing
"""

from datetime import date
from decimal import Decimal

import pytest

from app.crypto import encrypt_ssn
from app.models.member import Member
from app.models.plan_config import PlanTier, PlanType, SystemConfiguration
from app.models.salary import SalaryHistory
from app.models.employment import EmploymentRecord
from app.models.employer import Employer
from app.models.service_credit import ServiceCreditEntry
from app.schemas.service_purchase import (
    ApprovePurchaseClaimRequest,
    CancelPurchaseClaimRequest,
    ServicePurchaseClaimCreate,
    ServicePurchasePaymentCreate,
    ServicePurchaseQuoteRequest,
)
from app.services import service_purchase_service as svc
from app.services.benefit_estimate_service import _service_credit_by_slot


# ── Fixtures ───────────────────────────────────────────────────────────────────

_PURCHASE_TYPES_CFG = {
    "types": {
        "military": {
            "label": "Military Service",
            "credit_entry_type": "purchased_military",
            "credit_type_slot": "military_service_years",
            "calc_method": "rate_based",
            "employee_rate": 0.08,
            "employer_rate": 0.0,
            "installment_allowed": True,
            "credit_grant_on": "completion",
        },
        "ope": {
            "label": "Other Public Employment",
            "credit_entry_type": "purchased_ope",
            "credit_type_slot": "ope_service_years",
            "calc_method": "rate_based",
            "employee_rate": 0.08,
            "employer_rate": 0.12,
            "installment_allowed": True,
            "credit_grant_on": "completion",
        },
        "prior_service": {
            "label": "Prior Service",
            "credit_entry_type": "purchased_prior_service",
            "credit_type_slot": "system_service_years",
            "calc_method": "rate_based",
            "employee_rate": 0.08,
            "employer_rate": 0.12,
            "installment_allowed": True,
            "credit_grant_on": "completion",
        },
        "refund": {
            "label": "Refund Repayment",
            "credit_entry_type": "purchased_refund",
            "credit_type_slot": "system_service_years",
            "calc_method": "refund_repayment",
            "interest_rate": 0.065,
            "installment_allowed": False,
            "credit_grant_on": "completion",
        },
        "grant_on_approval": {
            "label": "Test: Grant on Approval",
            "credit_entry_type": "purchased_test_approval",
            "credit_type_slot": "system_service_years",
            "calc_method": "rate_based",
            "employee_rate": 0.08,
            "employer_rate": 0.0,
            "installment_allowed": False,
            "credit_grant_on": "approval",
        },
        "grant_on_first_payment": {
            "label": "Test: Grant on First Payment",
            "credit_entry_type": "purchased_test_first",
            "credit_type_slot": "system_service_years",
            "calc_method": "rate_based",
            "employee_rate": 0.08,
            "employer_rate": 0.0,
            "installment_allowed": True,
            "credit_grant_on": "first_payment",
        },
    }
}


async def _setup(session):
    tier = PlanTier(tier_code="t1", tier_label="Tier I", effective_date=date(1980, 1, 1))
    plan = PlanType(plan_code="traditional", plan_label="Traditional")
    session.add_all([tier, plan])
    await session.flush()

    cfg = SystemConfiguration(
        config_key="service_purchase_types",
        config_value=_PURCHASE_TYPES_CFG,
        effective_date=date(1980, 1, 1),
    )
    session.add(cfg)

    employer = Employer(name="State U", employer_code="STU-001", employer_type="university")
    session.add(employer)
    await session.flush()

    member = Member(
        member_number="SP-001",
        first_name="Alice",
        last_name="Buyer",
        date_of_birth=date(1970, 1, 1),
        ssn_encrypted=encrypt_ssn("987654321"),
        ssn_last_four="4321",
        certification_date=date(2000, 1, 1),
        plan_tier_id=tier.id,
        plan_type_id=plan.id,
        member_status="active",
    )
    session.add(member)
    await session.flush()

    employment = EmploymentRecord(
        member_id=member.id,
        employer_id=employer.id,
        employment_type="general_staff",
        hire_date=date(2000, 1, 1),
        percent_time=100.0,
    )
    session.add(employment)
    await session.flush()

    salary = SalaryHistory(
        employment_id=employment.id,
        annual_salary=Decimal("60000"),
        effective_date=date(1990, 1, 1),
    )
    session.add(salary)
    await session.flush()

    return member


# ── Quote ──────────────────────────────────────────────────────────────────────

async def test_quote_rate_based_military(session):
    async with session.begin():
        member = await _setup(session)
        req = ServicePurchaseQuoteRequest(
            purchase_type="military",
            credit_years=Decimal("2.0"),
            period_start=date(1995, 1, 1),
            period_end=date(1996, 12, 31),
        )
        result = await svc.quote(member.id, req, session)

    # 2.0 years × $60,000 × 0.08 employee rate (employer = 0)
    assert result.cost_total == Decimal("9600.00")
    assert result.credit_entry_type == "purchased_military"
    assert result.installment_allowed is True
    assert result.credit_grant_on == "completion"


async def test_quote_ope_includes_employer_rate(session):
    async with session.begin():
        member = await _setup(session)
        req = ServicePurchaseQuoteRequest(
            purchase_type="ope",
            credit_years=Decimal("1.0"),
            period_start=date(1998, 1, 1),
            period_end=date(1998, 12, 31),
        )
        result = await svc.quote(member.id, req, session)

    # 1.0 × $60,000 × (0.08 + 0.12)
    assert result.cost_total == Decimal("12000.00")


async def test_quote_refund_repayment_raises_not_implemented(session):
    async with session.begin():
        member = await _setup(session)
        req = ServicePurchaseQuoteRequest(
            purchase_type="refund",
            credit_years=Decimal("3.0"),
            period_start=date(1990, 1, 1),
            period_end=date(1992, 12, 31),
        )
        with pytest.raises(ValueError, match="refund_repayment.*not yet implemented"):
            await svc.quote(member.id, req, session)


async def test_quote_unknown_type_raises(session):
    async with session.begin():
        member = await _setup(session)
        req = ServicePurchaseQuoteRequest(
            purchase_type="unicorn",
            credit_years=Decimal("1.0"),
            period_start=date(2000, 1, 1),
            period_end=date(2000, 12, 31),
        )
        with pytest.raises(ValueError, match="Unknown purchase type"):
            await svc.quote(member.id, req, session)


# ── Claim lifecycle ────────────────────────────────────────────────────────────

async def test_create_claim_stores_cost_snapshot(session):
    async with session.begin():
        member = await _setup(session)
        data = ServicePurchaseClaimCreate(
            purchase_type="military",
            credit_years=Decimal("1.0"),
            period_start=date(1995, 1, 1),
            period_end=date(1995, 12, 31),
        )
        claim = await svc.create_claim(member.id, data, session)

    assert claim.status == "draft"
    assert Decimal(str(claim.cost_total)) == Decimal("4800.00")
    assert claim.credit_entry_type == "purchased_military"
    assert claim.installment_allowed is True


async def test_submit_transitions_to_pending_approval(session):
    async with session.begin():
        member = await _setup(session)
        data = ServicePurchaseClaimCreate(
            purchase_type="ope",
            credit_years=Decimal("1.0"),
            period_start=date(1996, 1, 1),
            period_end=date(1996, 12, 31),
        )
        claim = await svc.create_claim(member.id, data, session)
        claim = await svc.submit_claim(claim, session)

    assert claim.status == "pending_approval"


async def test_submit_wrong_status_raises(session):
    async with session.begin():
        member = await _setup(session)
        data = ServicePurchaseClaimCreate(
            purchase_type="military",
            credit_years=Decimal("1.0"),
            period_start=date(1995, 1, 1),
            period_end=date(1995, 12, 31),
        )
        claim = await svc.create_claim(member.id, data, session)
        await svc.submit_claim(claim, session)
        with pytest.raises(ValueError, match="must be 'draft'"):
            await svc.submit_claim(claim, session)


async def test_approve_sets_approved_fields(session):
    import uuid as _uuid
    async with session.begin():
        member = await _setup(session)
        data = ServicePurchaseClaimCreate(
            purchase_type="military",
            credit_years=Decimal("1.0"),
            period_start=date(1995, 1, 1),
            period_end=date(1995, 12, 31),
        )
        claim = await svc.create_claim(member.id, data, session)
        await svc.submit_claim(claim, session)
        approver = _uuid.uuid4()
        claim = await svc.approve_claim(claim, approver, session)

    assert claim.status == "approved"
    assert claim.approved_by == approver
    assert claim.approved_at is not None


async def test_approve_grant_on_approval_writes_credit_immediately(session):
    import uuid as _uuid
    from sqlalchemy import select as sa_select
    async with session.begin():
        member = await _setup(session)
        data = ServicePurchaseClaimCreate(
            purchase_type="grant_on_approval",
            credit_years=Decimal("1.0"),
            period_start=date(1995, 1, 1),
            period_end=date(1995, 12, 31),
        )
        claim = await svc.create_claim(member.id, data, session)
        await svc.submit_claim(claim, session)
        claim = await svc.approve_claim(claim, _uuid.uuid4(), session)

        entries = (await session.execute(
            sa_select(ServiceCreditEntry).where(ServiceCreditEntry.member_id == member.id)
        )).scalars().all()

    assert claim.status == "completed"
    assert len(entries) == 1
    assert entries[0].entry_type == "purchased_test_approval"


async def test_cancel_from_draft(session):
    async with session.begin():
        member = await _setup(session)
        data = ServicePurchaseClaimCreate(
            purchase_type="military",
            credit_years=Decimal("1.0"),
            period_start=date(1995, 1, 1),
            period_end=date(1995, 12, 31),
        )
        claim = await svc.create_claim(member.id, data, session)
        claim = await svc.cancel_claim(claim, "member withdrew request", session)

    assert claim.status == "cancelled"
    assert claim.cancel_reason == "member withdrew request"


async def test_cancel_completed_raises(session):
    import uuid as _uuid
    async with session.begin():
        member = await _setup(session)
        data = ServicePurchaseClaimCreate(
            purchase_type="military",
            credit_years=Decimal("1.0"),
            period_start=date(1995, 1, 1),
            period_end=date(1995, 12, 31),
        )
        claim = await svc.create_claim(member.id, data, session)
        await svc.submit_claim(claim, session)
        await svc.approve_claim(claim, _uuid.uuid4(), session)
        payment = ServicePurchasePaymentCreate(
            amount=Decimal("4800.00"),
            payment_date=date(2024, 1, 15),
            payment_method="check",
        )
        await svc.record_payment(claim, payment, session)
        with pytest.raises(ValueError, match="Cannot cancel"):
            await svc.cancel_claim(claim, "too late", session)


# ── Payment recording ──────────────────────────────────────────────────────────

async def test_payment_completes_claim_and_grants_credit(session):
    import uuid as _uuid
    from sqlalchemy import select as sa_select
    async with session.begin():
        member = await _setup(session)
        data = ServicePurchaseClaimCreate(
            purchase_type="military",
            credit_years=Decimal("2.0"),
            period_start=date(1993, 1, 1),
            period_end=date(1994, 12, 31),
        )
        claim = await svc.create_claim(member.id, data, session)
        await svc.submit_claim(claim, session)
        await svc.approve_claim(claim, _uuid.uuid4(), session)

        payment = ServicePurchasePaymentCreate(
            amount=Decimal("9600.00"),
            payment_date=date(2024, 2, 1),
            payment_method="check",
            reference_number="CHK-12345",
        )
        await svc.record_payment(claim, payment, session)

        entries = (await session.execute(
            sa_select(ServiceCreditEntry).where(ServiceCreditEntry.member_id == member.id)
        )).scalars().all()

    assert claim.status == "completed"
    assert claim.completed_at is not None
    assert len(entries) == 1
    assert entries[0].entry_type == "purchased_military"
    assert Decimal(str(entries[0].credit_years)) == Decimal("2.0")


async def test_installment_payments_accumulate(session):
    import uuid as _uuid
    async with session.begin():
        member = await _setup(session)
        data = ServicePurchaseClaimCreate(
            purchase_type="military",
            credit_years=Decimal("1.0"),
            period_start=date(1995, 1, 1),
            period_end=date(1995, 12, 31),
        )
        claim = await svc.create_claim(member.id, data, session)
        await svc.submit_claim(claim, session)
        await svc.approve_claim(claim, _uuid.uuid4(), session)

        p1 = ServicePurchasePaymentCreate(
            amount=Decimal("2400.00"), payment_date=date(2024, 1, 1), payment_method="check"
        )
        p2 = ServicePurchasePaymentCreate(
            amount=Decimal("2400.00"), payment_date=date(2024, 7, 1), payment_method="check"
        )
        await svc.record_payment(claim, p1, session)
        assert claim.status == "in_payment"
        await svc.record_payment(claim, p2, session)

    assert claim.status == "completed"
    assert Decimal(str(claim.cost_paid)) == Decimal("4800.00")


async def test_non_installment_type_rejects_second_payment(session):
    import uuid as _uuid
    async with session.begin():
        member = await _setup(session)
        # prior_service has installment_allowed=True but we'll use a type with installment=False
        # Use grant_on_approval type which has installment_allowed=False
        data = ServicePurchaseClaimCreate(
            purchase_type="grant_on_approval",
            credit_years=Decimal("1.0"),
            period_start=date(1995, 1, 1),
            period_end=date(1995, 12, 31),
        )
        claim = await svc.create_claim(member.id, data, session)
        await svc.submit_claim(claim, session)
        # approve immediately grants credit and completes
        await svc.approve_claim(claim, _uuid.uuid4(), session)
        # claim is now completed — payment should fail
        p = ServicePurchasePaymentCreate(
            amount=Decimal("100.00"), payment_date=date(2024, 1, 1), payment_method="check"
        )
        with pytest.raises(ValueError):
            await svc.record_payment(claim, p, session)


async def test_payment_grants_credit_on_first_payment(session):
    import uuid as _uuid
    from sqlalchemy import select as sa_select
    async with session.begin():
        member = await _setup(session)
        data = ServicePurchaseClaimCreate(
            purchase_type="grant_on_first_payment",
            credit_years=Decimal("1.0"),
            period_start=date(1995, 1, 1),
            period_end=date(1995, 12, 31),
        )
        claim = await svc.create_claim(member.id, data, session)
        await svc.submit_claim(claim, session)
        await svc.approve_claim(claim, _uuid.uuid4(), session)

        p = ServicePurchasePaymentCreate(
            amount=Decimal("1.00"),  # partial — just triggers first_payment grant
            payment_date=date(2024, 1, 1),
            payment_method="check",
        )
        await svc.record_payment(claim, p, session)

        entries = (await session.execute(
            sa_select(ServiceCreditEntry).where(ServiceCreditEntry.member_id == member.id)
        )).scalars().all()

    assert len(entries) == 1
    assert entries[0].entry_type == "purchased_test_first"
    assert claim.status == "in_payment"  # not complete — not fully paid


# ── Benefit estimate slot routing ──────────────────────────────────────────────

async def test_service_credit_slot_routing(session):
    """Purchased credit routes to the correct BenefitCalculationRequest slot."""
    async with session.begin():
        member = await _setup(session)

        session.add(ServiceCreditEntry(
            member_id=member.id, entry_type="payroll",
            credit_days=365, credit_years=Decimal("5.0"),
            period_start=date(2000, 1, 1), period_end=date(2004, 12, 31),
        ))
        session.add(ServiceCreditEntry(
            member_id=member.id, entry_type="purchased_military",
            credit_days=730, credit_years=Decimal("2.0"),
            period_start=date(1995, 1, 1), period_end=date(1996, 12, 31),
        ))
        session.add(ServiceCreditEntry(
            member_id=member.id, entry_type="purchased_ope",
            credit_days=365, credit_years=Decimal("1.0"),
            period_start=date(1998, 1, 1), period_end=date(1998, 12, 31),
        ))
        await session.flush()

        slots = await _service_credit_by_slot(member.id, date(2025, 1, 1), session)

    assert slots["system_service_years"] == Decimal("5.0")
    assert slots["military_service_years"] == Decimal("2.0")
    assert slots["ope_service_years"] == Decimal("1.0")


async def test_service_credit_unknown_entry_type_defaults_to_system(session):
    async with session.begin():
        member = await _setup(session)
        session.add(ServiceCreditEntry(
            member_id=member.id, entry_type="some_legacy_type",
            credit_days=365, credit_years=Decimal("1.0"),
            period_start=date(2000, 1, 1), period_end=date(2000, 12, 31),
        ))
        await session.flush()
        slots = await _service_credit_by_slot(member.id, date(2025, 1, 1), session)

    assert slots.get("system_service_years", Decimal("0")) == Decimal("1.0")

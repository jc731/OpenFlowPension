"""Tests for the net pay calculation engine."""

from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import BenefitPayment, DeductionOrder, TaxWithholdingElection
from app.models.plan_config import SystemConfiguration
from app.schemas.net_pay import (
    NetPayDeductionInput,
    NetPayRequest,
    NetPayTaxElectionInput,
)
from app.services.net_pay_service import (
    apply_net_pay,
    calculate_net_pay,
    calculate_net_pay_stateless,
    get_net_pay_preview,
)

PAYMENT_DATE = date(2025, 3, 1)
TAX_YEAR = 2025

FEDERAL_CONFIG = {
    "tax_year": 2025,
    "standard_withholding_deduction": {
        "single": 15000,
        "married_filing_separately": 15000,
        "head_of_household": 22500,
        "married_filing_jointly": 30000,
        "qualifying_surviving_spouse": 30000,
    },
    "brackets": {
        "single": [
            {"min": 0, "max": 11925, "rate": 0.10, "base_tax": 0},
            {"min": 11925, "max": 48475, "rate": 0.12, "base_tax": 1192.50},
            {"min": 48475, "max": 103350, "rate": 0.22, "base_tax": 5578.50},
            {"min": 103350, "max": 197300, "rate": 0.24, "base_tax": 17651.50},
            {"min": 197300, "max": 250525, "rate": 0.32, "base_tax": 40199.50},
            {"min": 250525, "max": 626350, "rate": 0.35, "base_tax": 57231.50},
            {"min": 626350, "max": None, "rate": 0.37, "base_tax": 188769.75},
        ],
        "married_filing_jointly": [
            {"min": 0, "max": 23850, "rate": 0.10, "base_tax": 0},
            {"min": 23850, "max": 96950, "rate": 0.12, "base_tax": 2385.00},
            {"min": 96950, "max": 206700, "rate": 0.22, "base_tax": 11157.00},
            {"min": 206700, "max": 394600, "rate": 0.24, "base_tax": 35302.00},
            {"min": 394600, "max": 501050, "rate": 0.32, "base_tax": 80397.00},
            {"min": 501050, "max": 751600, "rate": 0.35, "base_tax": 114462.00},
            {"min": 751600, "max": None, "rate": 0.37, "base_tax": 202154.50},
        ],
    },
}

ILLINOIS_CONFIG = {"tax_year": 2025, "rate": 0.0495}


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def member_id(session: AsyncSession):
    from app.models.member import Member
    from app.models.plan_config import PlanTier, PlanType
    import uuid

    tier = PlanTier(tier_code="t1", tier_label="Tier I", effective_date=date(1980, 1, 1))
    ptype = PlanType(plan_code="trad", plan_label="Traditional")
    session.add_all([tier, ptype])
    await session.flush()

    m = Member(
        member_number="NP-001",
        first_name="Net",
        last_name="Pay",
        date_of_birth=date(1960, 1, 1),
        certification_date=date(2000, 1, 1),
        plan_tier_id=tier.id,
        plan_type_id=ptype.id,
        ssn_encrypted=b"fake",
        ssn_last_four="0000",
        member_status="annuitant",
    )
    session.add(m)
    await session.flush()
    return m.id


@pytest_asyncio.fixture
async def payment(session: AsyncSession, member_id):
    p = BenefitPayment(
        member_id=member_id,
        period_start=date(2025, 3, 1),
        period_end=date(2025, 3, 31),
        payment_date=PAYMENT_DATE,
        gross_amount=3000.00,
        net_amount=3000.00,
        payment_type="annuity",
        payment_method="ach",
    )
    session.add(p)
    await session.flush()
    return p


@pytest_asyncio.fixture
async def tax_configs(session: AsyncSession):
    session.add(SystemConfiguration(
        config_key="federal_income_tax_withholding",
        config_value=FEDERAL_CONFIG,
        effective_date=date(2025, 1, 1),
    ))
    session.add(SystemConfiguration(
        config_key="illinois_income_tax",
        config_value=ILLINOIS_CONFIG,
        effective_date=date(2025, 1, 1),
    ))
    await session.flush()


# ── Pure calculation tests ─────────────────────────────────────────────────────

def test_no_deductions_no_tax():
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[],
        tax_elections=[],
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=None,
        illinois_tax_config=None,
    )
    assert result.gross_amount == Decimal("3000")
    assert result.net_amount == Decimal("3000")
    assert result.taxable_gross == Decimal("3000")
    assert result.total_deductions == Decimal("0")


def test_fixed_pretax_deduction_reduces_taxable_gross():
    deductions = [
        NetPayDeductionInput(
            description="Health Insurance",
            deduction_type="health_insurance",
            amount=Decimal("250"),
            is_pretax=True,
        )
    ]
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=deductions,
        tax_elections=[],
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=None,
        illinois_tax_config=None,
    )
    assert result.taxable_gross == Decimal("2750")
    assert result.net_amount == Decimal("2750")
    assert len(result.pretax_deductions) == 1


def test_percent_of_gross_deduction():
    deductions = [
        NetPayDeductionInput(
            description="Union Dues",
            deduction_type="union_dues",
            amount_type="percent_of_gross",
            amount=Decimal("0.01"),
            is_pretax=False,
        )
    ]
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=deductions,
        tax_elections=[],
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=None,
        illinois_tax_config=None,
    )
    assert result.posttax_deductions[0].amount == Decimal("30.00")
    assert result.net_amount == Decimal("2970.00")


def test_federal_tax_single_monthly():
    # $3000/mo gross, single filer, monthly
    # Annualized: $36,000
    # Subtract std deduction $15,000 → $21,000
    # Bracket: 10% on $11,925 = $1,192.50; 12% on ($21,000 - $11,925) = $1,089.00 → total $2,281.50
    # Per month: $2,281.50 / 12 = $190.13
    elections = [
        NetPayTaxElectionInput(
            jurisdiction="federal",
            filing_status="single",
        )
    ]
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[],
        tax_elections=elections,
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=FEDERAL_CONFIG,
        illinois_tax_config=None,
    )
    assert len(result.tax_withholdings) == 1
    assert result.tax_withholdings[0].deduction_type == "federal_tax"
    assert result.tax_withholdings[0].amount == Decimal("190.13")
    assert result.net_amount == Decimal("3000") - Decimal("190.13")


def test_federal_tax_exempt():
    elections = [
        NetPayTaxElectionInput(
            jurisdiction="federal",
            filing_status="single",
            exempt=True,
        )
    ]
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[],
        tax_elections=elections,
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=FEDERAL_CONFIG,
        illinois_tax_config=None,
    )
    assert result.tax_withholdings[0].amount == Decimal("0")


def test_illinois_tax():
    elections = [
        NetPayTaxElectionInput(jurisdiction="illinois", filing_status="single")
    ]
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[],
        tax_elections=elections,
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=None,
        illinois_tax_config=ILLINOIS_CONFIG,
    )
    # 3000 * 0.0495 = 148.50
    assert result.tax_withholdings[0].amount == Decimal("148.50")
    assert result.tax_withholdings[0].deduction_type == "illinois_tax"


def test_illinois_tax_applies_to_taxable_gross_after_pretax():
    deductions = [
        NetPayDeductionInput(
            description="Health Insurance",
            deduction_type="health_insurance",
            amount=Decimal("500"),
            is_pretax=True,
        )
    ]
    elections = [
        NetPayTaxElectionInput(jurisdiction="illinois", filing_status="single")
    ]
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=deductions,
        tax_elections=elections,
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=None,
        illinois_tax_config=ILLINOIS_CONFIG,
    )
    # taxable = 2500; IL = 2500 * 0.0495 = 123.75
    assert result.taxable_gross == Decimal("2500")
    assert result.tax_withholdings[0].amount == Decimal("123.75")


def test_full_check_stub_ordering():
    """Pre-tax → tax → post-tax applied in correct order; net is correct."""
    deductions = [
        NetPayDeductionInput(
            description="Health Insurance",
            deduction_type="health_insurance",
            amount=Decimal("200"),
            is_pretax=True,
        ),
        NetPayDeductionInput(
            description="Child Support",
            deduction_type="child_support",
            amount=Decimal("300"),
            is_pretax=False,
        ),
    ]
    elections = [
        NetPayTaxElectionInput(jurisdiction="illinois", filing_status="single")
    ]
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=deductions,
        tax_elections=elections,
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=None,
        illinois_tax_config=ILLINOIS_CONFIG,
    )
    # taxable = 3000 - 200 = 2800
    # IL tax = 2800 * 0.0495 = 138.60
    # net = 3000 - 200 - 138.60 - 300 = 2361.40
    assert result.taxable_gross == Decimal("2800")
    assert result.tax_withholdings[0].amount == Decimal("138.60")
    assert result.net_amount == Decimal("2361.40")
    assert result.total_deductions == Decimal("638.60")


def test_additional_withholding_added():
    elections = [
        NetPayTaxElectionInput(
            jurisdiction="illinois",
            filing_status="single",
            additional_withholding=Decimal("50"),
        )
    ]
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[],
        tax_elections=elections,
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=None,
        illinois_tax_config=ILLINOIS_CONFIG,
    )
    assert result.tax_withholdings[0].amount == Decimal("198.50")  # 148.50 + 50.00


# ── DB-backed tests ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_net_pay_preview_no_orders_no_elections(session, payment, tax_configs):
    result = await get_net_pay_preview(payment.id, session)
    assert result.gross_amount == Decimal("3000")
    assert result.net_amount == Decimal("3000")


@pytest.mark.asyncio
async def test_get_net_pay_preview_with_standing_order(session, payment, member_id, tax_configs):
    order = DeductionOrder(
        member_id=member_id,
        deduction_type="health_insurance",
        amount_type="fixed",
        amount=250.00,
        is_pretax=True,
        effective_date=date(2025, 1, 1),
    )
    session.add(order)
    await session.flush()

    result = await get_net_pay_preview(payment.id, session)
    assert result.taxable_gross == Decimal("2750")
    assert len(result.pretax_deductions) == 1


@pytest.mark.asyncio
async def test_get_net_pay_preview_with_w4_election(session, payment, member_id, tax_configs):
    election = TaxWithholdingElection(
        member_id=member_id,
        jurisdiction="illinois",
        filing_status="single",
        additional_withholding=0,
        exempt=False,
        effective_date=date(2025, 1, 1),
    )
    session.add(election)
    await session.flush()

    result = await get_net_pay_preview(payment.id, session)
    assert len(result.tax_withholdings) == 1
    assert result.tax_withholdings[0].deduction_type == "illinois_tax"
    assert result.tax_withholdings[0].amount == Decimal("148.50")


@pytest.mark.asyncio
async def test_apply_net_pay_persists_deductions(session, payment, member_id, tax_configs):
    session.add(TaxWithholdingElection(
        member_id=member_id,
        jurisdiction="illinois",
        filing_status="single",
        additional_withholding=0,
        exempt=False,
        effective_date=date(2025, 1, 1),
    ))
    await session.flush()

    result = await apply_net_pay(payment.id, session)

    await session.refresh(payment, ["deductions"])
    assert len(payment.deductions) == 1
    assert payment.deductions[0].deduction_type == "illinois_tax"
    assert float(payment.net_amount) == pytest.approx(2851.50, abs=0.01)


@pytest.mark.asyncio
async def test_apply_net_pay_idempotency_guard(session, payment, member_id, tax_configs):
    session.add(TaxWithholdingElection(
        member_id=member_id,
        jurisdiction="illinois",
        filing_status="single",
        additional_withholding=0,
        exempt=False,
        effective_date=date(2025, 1, 1),
    ))
    await session.flush()

    await apply_net_pay(payment.id, session)
    await session.flush()

    with pytest.raises(ValueError, match="already been applied"):
        await apply_net_pay(payment.id, session)


@pytest.mark.asyncio
async def test_stateless_endpoint_helper(session, tax_configs):
    req = NetPayRequest(
        gross_amount=Decimal("3000"),
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        tax_elections=[
            NetPayTaxElectionInput(jurisdiction="illinois", filing_status="single")
        ],
    )
    result = await calculate_net_pay_stateless(req, session)
    assert result.tax_withholdings[0].amount == Decimal("148.50")
    assert result.net_amount == Decimal("2851.50")

"""Tests for the net pay calculation engine."""

from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import BenefitPayment, DeductionOrder, TaxWithholdingElection
from app.models.plan_config import SystemConfiguration
from app.models.third_party_entity import ThirdPartyEntity
from app.schemas.net_pay import (
    NetPayDeductionInput,
    NetPayRequest,
    NetPayTaxElectionInput,
    ThirdPartyDisbursementInput,
)
from app.services.net_pay_service import (
    apply_net_pay,
    calculate_net_pay,
    calculate_net_pay_stateless,
    get_net_pay_preview,
)

PAYMENT_DATE = date(2025, 3, 1)

FEDERAL_CONFIG = {
    "tax_year": 2025,
    "standard_withholding_deduction": {
        "single": 15000,
        "married_filing_separately": 15000,
        "head_of_household": 22500,
        "married_filing_jointly": 30000,
        "qualifying_surviving_spouse": 30000,
    },
    "higher_withholding_deduction": {
        "single": 7500,
        "married_filing_separately": 7500,
        "head_of_household": 11250,
        "married_filing_jointly": 15000,
        "qualifying_surviving_spouse": 15000,
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


@pytest_asyncio.fixture
async def third_party_entity(session: AsyncSession):
    e = ThirdPartyEntity(name="Cook County Clerk", entity_type="court")
    session.add(e)
    await session.flush()
    return e


# ── Basic deduction tests ──────────────────────────────────────────────────────

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
    assert result.third_party_disbursements == []
    assert result.total_third_party_disbursements == Decimal("0")


def test_pretax_deduction_reduces_taxable_gross():
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[NetPayDeductionInput(
            description="Health Insurance", deduction_type="health_insurance",
            amount=Decimal("250"), is_pretax=True,
        )],
        tax_elections=[],
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=None,
        illinois_tax_config=None,
    )
    assert result.taxable_gross == Decimal("2750")
    assert result.net_amount == Decimal("2750")


def test_percent_of_gross_deduction():
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[NetPayDeductionInput(
            description="Union Dues", deduction_type="union_dues",
            amount_type="percent_of_gross", amount=Decimal("0.01"), is_pretax=False,
        )],
        tax_elections=[],
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=None,
        illinois_tax_config=None,
    )
    assert result.posttax_deductions[0].amount == Decimal("30.00")
    assert result.net_amount == Decimal("2970.00")


# ── Federal W-4P formula tests ─────────────────────────────────────────────────

def test_federal_basic_single_monthly():
    # $3000/mo gross, single, no W-4P adjustments
    # Annualized: $36,000 - $15,000 std = $21,000 taxable
    # Tax: 10% on $11,925 = $1,192.50; 12% on $9,075 = $1,089.00 → $2,281.50/yr
    # Per month: $2,281.50 / 12 = $190.13
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[],
        tax_elections=[NetPayTaxElectionInput(
            jurisdiction="federal", filing_status="single",
        )],
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=FEDERAL_CONFIG,
        illinois_tax_config=None,
    )
    assert result.tax_withholdings[0].deduction_type == "federal_tax"
    assert result.tax_withholdings[0].amount == Decimal("190.13")


def test_federal_step4a_other_income_increases_withholding():
    # Step 4(a) adds $12,000/yr other income → annualized wage = $36,000 + $12,000 = $48,000
    # Adjusted: $48,000 - $15,000 = $33,000
    # Tax: $1,192.50 + ($33,000 - $11,925) × 0.12 = $1,192.50 + $2,529.00 = $3,721.50
    # Per month: $3,721.50 / 12 = $310.13
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[],
        tax_elections=[NetPayTaxElectionInput(
            jurisdiction="federal", filing_status="single",
            step_4a_other_income=Decimal("12000"),
        )],
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=FEDERAL_CONFIG,
        illinois_tax_config=None,
    )
    assert result.tax_withholdings[0].amount == Decimal("310.13")


def test_federal_step4b_deductions_decrease_withholding():
    # Step 4(b) subtracts $6,000 additional deductions from adjusted income
    # Annualized: $36,000 - $15,000 - $6,000 = $15,000
    # Tax: $1,192.50 + ($15,000 - $11,925) × 0.12 = $1,192.50 + $369.00 = $1,561.50
    # Per month: $1,561.50 / 12 = $130.13
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[],
        tax_elections=[NetPayTaxElectionInput(
            jurisdiction="federal", filing_status="single",
            step_4b_deductions=Decimal("6000"),
        )],
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=FEDERAL_CONFIG,
        illinois_tax_config=None,
    )
    assert result.tax_withholdings[0].amount == Decimal("130.13")


def test_federal_step3_dependent_credit_reduces_tax():
    # Step 3: $2,000 dependent credit — subtracted from annual tax (not income)
    # Annual tax without credit: $2,281.50 (from basic test)
    # After credit: $2,281.50 - $2,000 = $281.50 / 12 = $23.46
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[],
        tax_elections=[NetPayTaxElectionInput(
            jurisdiction="federal", filing_status="single",
            step_3_dependent_credit=Decimal("2000"),
        )],
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=FEDERAL_CONFIG,
        illinois_tax_config=None,
    )
    assert result.tax_withholdings[0].amount == Decimal("23.46")


def test_federal_step3_credit_cannot_make_withholding_negative():
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[],
        tax_elections=[NetPayTaxElectionInput(
            jurisdiction="federal", filing_status="single",
            step_3_dependent_credit=Decimal("99999"),
        )],
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=FEDERAL_CONFIG,
        illinois_tax_config=None,
    )
    assert result.tax_withholdings[0].amount == Decimal("0")


def test_federal_step2_multiple_jobs_uses_higher_withholding_table():
    # Step 2 checked → std deduction halved: $7,500 instead of $15,000
    # Annualized: $36,000 - $7,500 = $28,500
    # Tax: $1,192.50 + ($28,500 - $11,925) × 0.12 = $1,192.50 + $1,989.00 = $3,181.50
    # Per month: $3,181.50 / 12 = $265.13
    result_step2 = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[],
        tax_elections=[NetPayTaxElectionInput(
            jurisdiction="federal", filing_status="single",
            step_2_multiple_jobs=True,
        )],
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=FEDERAL_CONFIG,
        illinois_tax_config=None,
    )
    result_no_step2 = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[],
        tax_elections=[NetPayTaxElectionInput(
            jurisdiction="federal", filing_status="single",
        )],
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=FEDERAL_CONFIG,
        illinois_tax_config=None,
    )
    # Step 2 should produce higher withholding
    assert result_step2.tax_withholdings[0].amount > result_no_step2.tax_withholdings[0].amount
    assert result_step2.tax_withholdings[0].amount == Decimal("265.13")


def test_federal_additional_withholding_added_on_top():
    # Formula gives $190.13 + $50 extra = $240.13
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[],
        tax_elections=[NetPayTaxElectionInput(
            jurisdiction="federal", filing_status="single",
            additional_withholding=Decimal("50"),
        )],
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=FEDERAL_CONFIG,
        illinois_tax_config=None,
    )
    assert result.tax_withholdings[0].amount == Decimal("240.13")


def test_federal_married_filing_jointly():
    # $3000/mo, MFJ, no adjustments
    # Annualized: $36,000 - $30,000 = $6,000 taxable
    # Tax: 10% × $6,000 = $600 / 12 = $50.00
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[],
        tax_elections=[NetPayTaxElectionInput(
            jurisdiction="federal", filing_status="married_filing_jointly",
        )],
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=FEDERAL_CONFIG,
        illinois_tax_config=None,
    )
    assert result.tax_withholdings[0].amount == Decimal("50.00")


def test_federal_exempt():
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[],
        tax_elections=[NetPayTaxElectionInput(
            jurisdiction="federal", filing_status="single",
            withholding_type="exempt",
        )],
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=FEDERAL_CONFIG,
        illinois_tax_config=None,
    )
    assert result.tax_withholdings[0].amount == Decimal("0")


def test_federal_flat_amount():
    # flat_amount: withhold exactly $125 per period regardless of income
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[],
        tax_elections=[NetPayTaxElectionInput(
            jurisdiction="federal", filing_status="single",
            withholding_type="flat_amount",
            additional_withholding=Decimal("125"),
        )],
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=FEDERAL_CONFIG,
        illinois_tax_config=None,
    )
    assert result.tax_withholdings[0].amount == Decimal("125.00")


def test_federal_legacy_exempt_flag_still_works():
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[],
        tax_elections=[NetPayTaxElectionInput(
            jurisdiction="federal", filing_status="single",
            exempt=True,
        )],
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=FEDERAL_CONFIG,
        illinois_tax_config=None,
    )
    assert result.tax_withholdings[0].amount == Decimal("0")


# ── Illinois tax tests ─────────────────────────────────────────────────────────

def test_illinois_basic():
    # 3000 * 0.0495 = 148.50
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[],
        tax_elections=[NetPayTaxElectionInput(jurisdiction="illinois", filing_status="single")],
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=None,
        illinois_tax_config=ILLINOIS_CONFIG,
    )
    assert result.tax_withholdings[0].amount == Decimal("148.50")
    assert result.tax_withholdings[0].deduction_type == "illinois_tax"


def test_illinois_no_state_tax_exempt():
    """withholding_type='exempt' is the explicit 'no state tax' option."""
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[],
        tax_elections=[NetPayTaxElectionInput(
            jurisdiction="illinois", filing_status="single",
            withholding_type="exempt",
        )],
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=None,
        illinois_tax_config=ILLINOIS_CONFIG,
    )
    assert result.tax_withholdings[0].amount == Decimal("0")


def test_illinois_flat_amount():
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[],
        tax_elections=[NetPayTaxElectionInput(
            jurisdiction="illinois", filing_status="single",
            withholding_type="flat_amount",
            additional_withholding=Decimal("75"),
        )],
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=None,
        illinois_tax_config=ILLINOIS_CONFIG,
    )
    assert result.tax_withholdings[0].amount == Decimal("75.00")


def test_illinois_applies_to_taxable_gross_after_pretax():
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[NetPayDeductionInput(
            description="Health Insurance", deduction_type="health_insurance",
            amount=Decimal("500"), is_pretax=True,
        )],
        tax_elections=[NetPayTaxElectionInput(jurisdiction="illinois", filing_status="single")],
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=None,
        illinois_tax_config=ILLINOIS_CONFIG,
    )
    assert result.taxable_gross == Decimal("2500")
    assert result.tax_withholdings[0].amount == Decimal("123.75")


def test_no_state_election_means_no_state_tax():
    """If no Illinois election exists, no state tax is computed — implicit 'no state tax'."""
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[],
        tax_elections=[],
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=None,
        illinois_tax_config=ILLINOIS_CONFIG,
    )
    assert result.tax_withholdings == []
    assert result.total_taxes == Decimal("0")


# ── Third-party disbursements tier ────────────────────────────────────────────

def test_third_party_disbursements_in_own_section():
    import uuid
    eid = uuid.uuid4()
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[],
        tax_elections=[],
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=None,
        illinois_tax_config=None,
        third_party_disbursements=[ThirdPartyDisbursementInput(
            third_party_entity_id=eid,
            description="Child Support Order #12345",
            deduction_type="child_support",
            amount=Decimal("400"),
        )],
        third_party_names={eid: "Cook County Clerk"},
    )
    assert result.posttax_deductions == []
    assert len(result.third_party_disbursements) == 1
    line = result.third_party_disbursements[0]
    assert line.amount == Decimal("400")
    assert line.third_party_entity_id == eid
    assert line.third_party_entity_name == "Cook County Clerk"
    assert line.deduction_type == "child_support"
    assert result.total_third_party_disbursements == Decimal("400")
    assert result.net_amount == Decimal("2600")


def test_third_party_disbursements_reduce_net_after_posttax():
    """Order of operations: posttax applied, then third-party, then net."""
    result = calculate_net_pay(
        gross=Decimal("3000"),
        deductions=[
            NetPayDeductionInput(
                description="Health", deduction_type="health_insurance",
                amount=Decimal("200"), is_pretax=True,
            ),
            NetPayDeductionInput(
                description="Dental", deduction_type="dental",
                amount=Decimal("50"), is_pretax=False,
            ),
        ],
        tax_elections=[NetPayTaxElectionInput(
            jurisdiction="illinois", filing_status="single",
        )],
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=None,
        illinois_tax_config=ILLINOIS_CONFIG,
        third_party_disbursements=[ThirdPartyDisbursementInput(
            third_party_entity_id=__import__("uuid").uuid4(),
            description="Union Dues",
            deduction_type="union_dues",
            amount=Decimal("30"),
        )],
    )
    # taxable = 3000 - 200 = 2800; IL = 2800 × 0.0495 = 138.60
    # net = 3000 - 200 - 138.60 - 50 - 30 = 2581.40
    assert result.taxable_gross == Decimal("2800")
    assert result.tax_withholdings[0].amount == Decimal("138.60")
    assert result.total_posttax_deductions == Decimal("50")
    assert result.total_third_party_disbursements == Decimal("30")
    assert result.net_amount == Decimal("2581.40")
    assert result.total_deductions == Decimal("418.60")


# ── Full check-stub test ───────────────────────────────────────────────────────

def test_full_check_stub_all_tiers():
    """All four tiers computed correctly with correct totals."""
    import uuid
    eid = uuid.uuid4()
    result = calculate_net_pay(
        gross=Decimal("4000"),
        deductions=[
            NetPayDeductionInput(
                description="Health", deduction_type="health_insurance",
                amount=Decimal("300"), is_pretax=True,
            ),
            NetPayDeductionInput(
                description="Dental", deduction_type="dental",
                amount=Decimal("60"), is_pretax=False,
            ),
        ],
        tax_elections=[
            NetPayTaxElectionInput(
                jurisdiction="federal", filing_status="single",
                step_3_dependent_credit=Decimal("500"),
            ),
            NetPayTaxElectionInput(jurisdiction="illinois", filing_status="single"),
        ],
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        federal_tax_config=FEDERAL_CONFIG,
        illinois_tax_config=ILLINOIS_CONFIG,
        third_party_disbursements=[ThirdPartyDisbursementInput(
            third_party_entity_id=eid,
            description="Garnishment",
            deduction_type="garnishment",
            amount=Decimal("200"),
        )],
        third_party_names={eid: "State of Illinois"},
    )
    # taxable_gross = 4000 - 300 = 3700
    assert result.taxable_gross == Decimal("3700")
    # federal: annualized 3700×12=44400 + 0 = 44400; -15000 std = 29400
    #   tax: 1192.50 + (29400-11925)×0.12 = 1192.50+2097.00=3289.50; -500 credit=2789.50; /12=232.46
    assert result.tax_withholdings[0].deduction_type == "federal_tax"
    assert result.tax_withholdings[0].amount == Decimal("232.46")
    # IL: 3700 × 0.0495 = 183.15
    assert result.tax_withholdings[1].deduction_type == "illinois_tax"
    assert result.tax_withholdings[1].amount == Decimal("183.15")
    assert result.total_posttax_deductions == Decimal("60")
    assert result.total_third_party_disbursements == Decimal("200")
    expected_net = Decimal("4000") - Decimal("300") - Decimal("232.46") - Decimal("183.15") - Decimal("60") - Decimal("200")
    assert result.net_amount == expected_net


# ── DB-backed tests ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_preview_no_orders_no_elections(session, payment, tax_configs):
    result = await get_net_pay_preview(payment.id, session)
    assert result.gross_amount == Decimal("3000")
    assert result.net_amount == Decimal("3000")
    assert result.third_party_disbursements == []


@pytest.mark.asyncio
async def test_preview_deduction_order_no_entity_goes_to_posttax(session, payment, member_id, tax_configs):
    session.add(DeductionOrder(
        member_id=member_id, deduction_type="dental",
        amount_type="fixed", amount=60.00, is_pretax=False,
        effective_date=date(2025, 1, 1),
    ))
    await session.flush()

    result = await get_net_pay_preview(payment.id, session)
    assert len(result.posttax_deductions) == 1
    assert result.third_party_disbursements == []


@pytest.mark.asyncio
async def test_preview_deduction_order_with_entity_goes_to_third_party(
    session, payment, member_id, tax_configs, third_party_entity
):
    session.add(DeductionOrder(
        member_id=member_id, deduction_type="child_support",
        amount_type="fixed", amount=400.00, is_pretax=False,
        effective_date=date(2025, 1, 1),
        third_party_entity_id=third_party_entity.id,
    ))
    await session.flush()

    result = await get_net_pay_preview(payment.id, session)
    assert result.posttax_deductions == []
    assert len(result.third_party_disbursements) == 1
    assert result.third_party_disbursements[0].third_party_entity_name == "Cook County Clerk"
    assert result.net_amount == Decimal("2600")


@pytest.mark.asyncio
async def test_preview_w4p_full_formula_from_db(session, payment, member_id, tax_configs):
    session.add(TaxWithholdingElection(
        member_id=member_id,
        jurisdiction="federal",
        filing_status="single",
        withholding_type="formula",
        additional_withholding=0,
        step_3_dependent_credit=2000,
        effective_date=date(2025, 1, 1),
    ))
    await session.flush()

    result = await get_net_pay_preview(payment.id, session)
    # Annual tax $2,281.50 - $2,000 = $281.50 / 12 = $23.46
    assert result.tax_withholdings[0].amount == Decimal("23.46")


@pytest.mark.asyncio
async def test_preview_w4p_exempt_from_db(session, payment, member_id, tax_configs):
    session.add(TaxWithholdingElection(
        member_id=member_id,
        jurisdiction="illinois",
        filing_status="single",
        withholding_type="exempt",
        additional_withholding=0,
        effective_date=date(2025, 1, 1),
    ))
    await session.flush()

    result = await get_net_pay_preview(payment.id, session)
    assert result.tax_withholdings[0].amount == Decimal("0")


@pytest.mark.asyncio
async def test_apply_net_pay_persists_all_tiers(
    session, payment, member_id, tax_configs, third_party_entity
):
    session.add(TaxWithholdingElection(
        member_id=member_id, jurisdiction="illinois", filing_status="single",
        withholding_type="formula", additional_withholding=0,
        effective_date=date(2025, 1, 1),
    ))
    session.add(DeductionOrder(
        member_id=member_id, deduction_type="child_support",
        amount_type="fixed", amount=400.00, is_pretax=False,
        effective_date=date(2025, 1, 1),
        third_party_entity_id=third_party_entity.id,
    ))
    await session.flush()

    result = await apply_net_pay(payment.id, session)

    await session.refresh(payment, ["deductions"])
    deduction_types = {d.deduction_type for d in payment.deductions}
    assert "illinois_tax" in deduction_types
    assert "child_support" in deduction_types
    # net = 3000 - 148.50 (IL) - 400 (child support) = 2451.50
    assert float(payment.net_amount) == pytest.approx(2451.50, abs=0.01)


@pytest.mark.asyncio
async def test_apply_net_pay_idempotency_guard(session, payment, member_id, tax_configs):
    session.add(TaxWithholdingElection(
        member_id=member_id, jurisdiction="illinois", filing_status="single",
        withholding_type="formula", additional_withholding=0,
        effective_date=date(2025, 1, 1),
    ))
    await session.flush()

    await apply_net_pay(payment.id, session)
    await session.flush()

    with pytest.raises(ValueError, match="already been applied"):
        await apply_net_pay(payment.id, session)


@pytest.mark.asyncio
async def test_stateless_endpoint_w4p_with_disbursement(session, tax_configs, third_party_entity):
    import uuid
    req = NetPayRequest(
        gross_amount=Decimal("3000"),
        payment_date=PAYMENT_DATE,
        pay_frequency="monthly",
        tax_elections=[
            NetPayTaxElectionInput(
                jurisdiction="illinois", filing_status="single",
            )
        ],
        third_party_disbursements=[ThirdPartyDisbursementInput(
            third_party_entity_id=third_party_entity.id,
            description="Child Support",
            deduction_type="child_support",
            amount=Decimal("300"),
        )],
    )
    result = await calculate_net_pay_stateless(req, session)
    # IL: 148.50; child support: 300; net = 3000 - 148.50 - 300 = 2551.50
    assert result.tax_withholdings[0].amount == Decimal("148.50")
    assert result.total_third_party_disbursements == Decimal("300")
    assert result.net_amount == Decimal("2551.50")
    assert result.third_party_disbursements[0].third_party_entity_name == "Cook County Clerk"

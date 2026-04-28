"""Tests for the benefit calculation engine.

All tests are pure computation — no database required.
Based on the MVP Jane Smith scenario (Tier I Traditional, 25 years, $72K FAE).
"""

from datetime import date
from decimal import Decimal

import pytest

from app.schemas.benefit import (
    BenefitCalculationRequest,
    BenefitOptionRequest,
    MoneyPurchaseContributions,
    SalaryPeriod,
)
from app.services.benefit.aai import compute_aai
from app.services.benefit.age_reduction import compute_age_reduction
from app.services.benefit.calculator import calculate_benefit
from app.services.benefit.eligibility import (
    age_years_months,
    check_eligibility,
    determine_tier,
)
from app.services.benefit.fae import (
    apply_spike_cap,
    build_academic_year_earnings,
    compute_fae,
)
from app.services.benefit.formulas.general import compute_general_annual
from app.services.benefit.max_cap import determine_benefit_cap
from app.services.benefit.service_credit import sick_leave_credit


# ── Jane Smith fixture ─────────────────────────────────────────────────────────

JANE_SALARY_HISTORY = [
    SalaryPeriod(start_date=date(2000, 1, 15), end_date=date(2005, 8, 31), annual_salary=Decimal("45000")),
    SalaryPeriod(start_date=date(2005, 9, 1), end_date=date(2012, 8, 31), annual_salary=Decimal("52000")),
    SalaryPeriod(start_date=date(2012, 9, 1), end_date=date(2019, 8, 31), annual_salary=Decimal("62000")),
    SalaryPeriod(start_date=date(2019, 9, 1), end_date=date(2025, 1, 15), annual_salary=Decimal("72000")),
]


def jane_request(**overrides) -> BenefitCalculationRequest:
    defaults = dict(
        plan_type="traditional",
        cert_date=date(2000, 1, 15),
        birth_date=date(1965, 3, 15),
        retirement_date=date(2025, 1, 15),
        termination_date=date(2025, 1, 15),
        system_service_years=Decimal("25"),
        salary_history=JANE_SALARY_HISTORY,
    )
    defaults.update(overrides)
    return BenefitCalculationRequest(**defaults)


# ── Unit: eligibility ──────────────────────────────────────────────────────────

def test_tier_determination():
    assert determine_tier(date(2000, 1, 15)) == "I"
    assert determine_tier(date(2011, 1, 1)) == "II"
    assert determine_tier(date(2010, 12, 31)) == "I"


def test_age_calculation():
    years, months = age_years_months(date(1965, 3, 15), date(2025, 1, 15))
    assert years == 59
    assert months == 10


def test_tier1_eligibility_age55_8yrs():
    eligible, _ = check_eligibility("I", date(1965, 3, 15), date(2025, 1, 15), date(2025, 1, 15), Decimal("25"))
    assert eligible


def test_tier1_eligibility_30_yrs_any_age():
    eligible, _ = check_eligibility("I", date(1975, 1, 1), date(2010, 1, 1), date(2010, 1, 1), Decimal("30"))
    assert eligible


def test_tier2_eligibility_62_10yrs():
    eligible, _ = check_eligibility("II", date(1963, 1, 1), date(2025, 2, 1), date(2025, 2, 1), Decimal("10"))
    assert eligible


def test_tier2_ineligible_insufficient_service():
    eligible, reason = check_eligibility("II", date(1963, 1, 1), date(2025, 2, 1), date(2025, 2, 1), Decimal("9"))
    assert not eligible
    assert "10+ years" in reason


# ── Unit: FAE ─────────────────────────────────────────────────────────────────

def test_academic_year_earnings_single_period():
    """A full AY at $72K should return $72K (within rounding of days/365)."""
    periods = [
        SalaryPeriod(start_date=date(2020, 7, 1), end_date=date(2021, 6, 30), annual_salary=Decimal("72000")),
    ]
    earnings = build_academic_year_earnings(periods)
    ay_2020 = date(2020, 7, 1)
    assert ay_2020 in earnings
    # 366 days in AY 2020-21 (due to Jul 1, 2020 to Jun 30, 2021, which spans a leap year)
    # earnings = 72000 / 365 * 366 = 72197... but actual days in period is 365 (366-1 because it's 365 days from Jul 1 to Jun 30)
    # The difference is small; just check it's close to 72000
    assert abs(earnings[ay_2020] - Decimal("72000")) < Decimal("300")


def test_fae_high_4_uses_best_consecutive_years():
    """Jane's best 4 consecutive AYs should be at the $72K rate. AY 2023-24 spans
    a leap year (366 days), so earnings = 72000 * 366/365 ≈ 72197. The 4-year window
    2020-21 through 2023-24 gives FAE slightly above $72,000."""
    fae, method, earnings = compute_fae(JANE_SALARY_HISTORY, "I", date(2025, 1, 15))
    assert method == "high_4"
    # FAE should be in the $72K range (leap year adds minor variation)
    assert Decimal("72000") <= fae <= Decimal("72200")


def test_spike_cap_applied():
    """A 25% raise should be capped at 20%."""
    ay_2019 = date(2019, 7, 1)
    ay_2020 = date(2020, 7, 1)
    raw = {ay_2019: Decimal("60000"), ay_2020: Decimal("75000")}  # 25% increase
    capped = apply_spike_cap(raw)
    assert capped[ay_2020] == Decimal("72000.00")  # 60000 * 1.20


def test_spike_cap_not_applied_under_20pct():
    ay_2019 = date(2019, 7, 1)
    ay_2020 = date(2020, 7, 1)
    raw = {ay_2019: Decimal("60000"), ay_2020: Decimal("70000")}  # 16.7% increase
    capped = apply_spike_cap(raw)
    assert capped[ay_2020] == Decimal("70000")


# ── Unit: General Formula ─────────────────────────────────────────────────────

def test_general_formula_post_1997():
    annual = compute_general_annual(Decimal("25"), Decimal("72000"), date(2025, 1, 15))
    assert annual == Decimal("39600.00")  # 25 * 0.022 * 72000


def test_general_formula_pre_1997_graduated():
    # 12 years service: 10 @ 1.67% + 2 @ 1.90%
    annual = compute_general_annual(Decimal("12"), Decimal("60000"), date(1995, 1, 1))
    expected = (10 * Decimal("0.0167") + 2 * Decimal("0.0190")) * 60000
    assert annual == expected.quantize(Decimal("0.01"))


# ── Unit: age reduction ────────────────────────────────────────────────────────

def test_age_reduction_tier1_2_months_short():
    months, factor = compute_age_reduction("I", date(1965, 3, 15), date(2025, 1, 15), Decimal("25"))
    assert months == 2
    assert factor == Decimal("0.99")


def test_no_age_reduction_tier1_30_years():
    months, factor = compute_age_reduction("I", date(1975, 1, 1), date(2025, 1, 1), Decimal("30"))
    assert months == 0
    assert factor == Decimal("1")


def test_no_age_reduction_tier1_past_60():
    months, factor = compute_age_reduction("I", date(1960, 1, 1), date(2025, 1, 1), Decimal("20"))
    assert months == 0
    assert factor == Decimal("1")


def test_age_reduction_tier2_5_years_short():
    # Born 1960-01-01, retires at 62 → 60 months short of 67
    months, factor = compute_age_reduction("II", date(1960, 1, 1), date(2022, 1, 1), Decimal("10"))
    assert months == 60
    assert factor == Decimal("0.7")  # 1 - 60*0.005


# ── Unit: max cap ─────────────────────────────────────────────────────────────

def test_cap_80pct_modern():
    pct = determine_benefit_cap(date(2025, 1, 15), 59, date(2000, 1, 15))
    assert pct == Decimal("80")


def test_cap_pre_1997_cert_after_1977():
    """cert >= 1977-09-15 + term before 1997-07-07 → 75%."""
    pct = determine_benefit_cap(date(1990, 1, 1), 60, date(1985, 1, 1))
    assert pct == Decimal("75")


# ── Unit: sick leave credit ────────────────────────────────────────────────────

def test_sick_leave_credit_180_days():
    credit = sick_leave_credit(200, date(2025, 1, 15), date(2025, 1, 15))
    assert credit == Decimal("1.00")


def test_sick_leave_credit_60_days():
    credit = sick_leave_credit(60, date(2025, 1, 15), date(2025, 1, 15))
    assert credit == Decimal("0.50")


def test_sick_leave_credit_no_credit_under_20():
    credit = sick_leave_credit(15, date(2025, 1, 15), date(2025, 1, 15))
    assert credit == Decimal("0")


def test_sick_leave_credit_too_late():
    credit = sick_leave_credit(200, date(2025, 4, 1), date(2025, 1, 15))
    assert credit == Decimal("0")


# ── Unit: AAI ─────────────────────────────────────────────────────────────────

def test_aai_tier1_first_increase_date():
    rate, first_date, _ = compute_aai("I", date(2025, 1, 15), date(1965, 3, 15), Decimal("3267"))
    assert rate == "3pct_compound"
    assert first_date == date(2026, 1, 1)


def test_aai_tier2_delayed_to_age_67():
    # Born 1975-01-01, retires at 62 on 2037-01-01
    # Age 67 birthday = 2042-01-01 > first anniversary 2038-01-01
    # "Jan 1 on or after age 67" = Jan 1, 2042 (the birthday itself is Jan 1)
    rate, first_date, _ = compute_aai("II", date(2037, 1, 1), date(1975, 1, 1), Decimal("2000"))
    assert rate == "cpi_u_half"
    assert first_date == date(2042, 1, 1)


# ── Integration: full Jane Smith calculation ───────────────────────────────────

def test_jane_smith_full_calculation():
    req = jane_request()
    result = calculate_benefit(req)

    assert result.tier == "I"
    assert result.plan_type == "traditional"

    # Service credit
    assert result.service_credit.system_service == Decimal("25.00")
    assert result.service_credit.sick_leave_credit == Decimal("0")
    assert result.service_credit.total == Decimal("25.00")

    # FAE: best 4 consecutive AYs at $72K rate. Leap year (AY 2023-24 = 366 days)
    # causes FAE to be slightly above $72,000 — this is the correct computed value.
    assert result.fae.method_used == "high_4"
    assert Decimal("72000") <= result.fae.annual <= Decimal("72200")

    # General formula
    gf = result.formulas.general
    assert gf.applicable is True
    # unreduced_annual = 25 * 0.022 * fae ≈ 39600–39644
    assert Decimal("39600") <= gf.unreduced_annual <= Decimal("39650")
    # unreduced_monthly = annual / 12
    assert Decimal("3300") <= gf.unreduced_monthly <= Decimal("3305")
    assert gf.age_reduction_months == 2
    assert gf.age_reduction_factor == Decimal("0.990000")
    # reduced_monthly = unreduced * 0.99
    assert Decimal("3267") <= gf.reduced_monthly <= Decimal("3275")

    # Formula selection
    assert result.formula_selected == "general"
    assert result.base_unreduced_annuity_monthly == gf.reduced_monthly

    # No cap applied (reduced < 80% of FAE / 12)
    assert result.maximum_benefit_cap.capped is False
    assert result.maximum_benefit_cap.percentage == Decimal("80")

    # No benefit option elected
    assert result.benefit_option.option_type == "single_life"
    assert result.benefit_option.reduction_amount == Decimal("0")

    # AAI
    assert result.aai.rate_type == "3pct_compound"
    assert result.aai.first_increase_date == date(2026, 1, 1)

    # HB2616 minimum (25 * $25 = $625 < final annuity → no supplemental)
    assert result.hb2616_minimum.minimum_monthly == Decimal("625.00")
    assert result.hb2616_minimum.supplemental_payment == Decimal("0.00")

    # Final annuity matches reduced general benefit
    assert result.final_monthly_annuity == gf.reduced_monthly


def test_jane_smith_with_sick_leave():
    """60 sick days → 0.5 year credit → total service = 25.5 years → higher benefit."""
    req = jane_request(sick_leave_days=60)
    result = calculate_benefit(req)

    assert result.service_credit.sick_leave_credit == Decimal("0.50")
    assert result.service_credit.total == Decimal("25.50")
    # 25.5 * 0.022 * fae / 12 — slightly above 25.5 * 0.022 * 72000 / 12 = 3366 due to leap year
    base = result.formulas.general
    assert base.unreduced_monthly > Decimal("3366")
    assert base.unreduced_monthly < Decimal("3380")


def test_mp_not_applicable_cert_after_2005():
    """cert_date >= 2005-07-01 → Money Purchase not applicable."""
    req = jane_request(
        cert_date=date(2011, 1, 1),
        money_purchase_contributions=MoneyPurchaseContributions(normal_ci=Decimal("100000")),
        mp_actuarial_factor=Decimal("150"),
    )
    result = calculate_benefit(req)
    assert result.formulas.money_purchase.applicable is False


def test_mp_applicable_cert_before_2005():
    """cert_date < 2005-07-01 → MP calculated and compared."""
    req = jane_request(
        cert_date=date(2000, 1, 15),
        money_purchase_contributions=MoneyPurchaseContributions(normal_ci=Decimal("500000")),
        mp_actuarial_factor=Decimal("150"),
    )
    result = calculate_benefit(req)
    # standard_mp = (500000 * 2.4) / 150 = 8000/month
    assert result.formulas.money_purchase.applicable is True
    assert result.formulas.money_purchase.standard_monthly == Decimal("8000.00")
    # MP wins over General ($3267)
    assert result.formula_selected == "money_purchase"


def test_hb2616_minimum_floor():
    """Member with very low benefit should get supplemental payment."""
    req = BenefitCalculationRequest(
        plan_type="traditional",
        cert_date=date(2000, 1, 15),
        birth_date=date(1945, 3, 15),  # age 79 at retirement
        retirement_date=date(2025, 1, 15),
        termination_date=date(2025, 1, 15),
        system_service_years=Decimal("8"),
        salary_history=[
            SalaryPeriod(start_date=date(2017, 1, 1), end_date=date(2025, 1, 15), annual_salary=Decimal("10000")),
        ],
    )
    result = calculate_benefit(req)
    # General: 8 * 0.022 * 10000 / 12 = $146.67
    # HB2616 min: 8 * $25 = $200
    assert result.hb2616_minimum.supplemental_payment > Decimal("0")
    assert result.hb2616_minimum.minimum_monthly == Decimal("200.00")

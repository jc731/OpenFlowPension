"""Tests for FundConfig loading and the parameterized calculation engine."""

from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.fund_config import FormulaBand, FundConfig, SickLeaveStep
from app.services.fund_config_service import load_fund_config
from app.services.benefit.aai import compute_aai
from app.services.benefit.age_reduction import compute_age_reduction
from app.services.benefit.eligibility import determine_tier
from app.services.benefit.fae import apply_spike_cap
from app.services.benefit.formulas.general import compute_general_annual
from app.services.benefit.formulas.money_purchase import is_mp_eligible
from app.services.benefit.formulas.police_fire import check_pf_eligibility, compute_police_fire_monthly
from app.services.benefit.max_cap import determine_benefit_cap
from app.services.benefit.service_credit import sick_leave_credit

# ---------------------------------------------------------------------------
# FundConfig defaults
# ---------------------------------------------------------------------------

def test_fund_config_defaults_are_surs():
    cfg = FundConfig()
    assert cfg.tier_cutoff_date == date(2011, 1, 1)
    assert cfg.fae_tier_i_years == 4
    assert cfg.fae_tier_ii_years == 8
    assert cfg.general_formula_multiplier == Decimal("0.022")
    assert cfg.cola_tier_i_type == "3pct_compound"
    assert cfg.sick_leave_method == "step_table"
    assert cfg.hb2616_enabled is True
    assert cfg.mp_eligibility_cutoff_date == date(2005, 7, 1)


def test_fund_config_roundtrip():
    cfg = FundConfig(
        tier_cutoff_date=date(2011, 1, 1),
        fae_tier_i_years=4,
        cola_tier_i_type="3pct_simple",
    )
    dumped = cfg.model_dump(mode="json")
    restored = FundConfig.model_validate(dumped)
    assert restored.cola_tier_i_type == "3pct_simple"
    assert restored.fae_tier_i_years == 4


# ---------------------------------------------------------------------------
# fund_config_service — DB load
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_load_fund_config_returns_defaults_when_key_absent(session: AsyncSession):
    cfg = await load_fund_config(date.today(), session)
    assert isinstance(cfg, FundConfig)
    assert cfg.tier_cutoff_date == date(2011, 1, 1)


# ---------------------------------------------------------------------------
# Parameterized eligibility
# ---------------------------------------------------------------------------

def test_determine_tier_custom_cutoff():
    # Fund with a 2015 cutoff
    assert determine_tier(date(2014, 12, 31), tier_cutoff_date=date(2015, 1, 1)) == "I"
    assert determine_tier(date(2015, 1, 1), tier_cutoff_date=date(2015, 1, 1)) == "II"


# ---------------------------------------------------------------------------
# Parameterized spike cap
# ---------------------------------------------------------------------------

def test_spike_cap_disabled():
    earnings = {
        date(2020, 7, 1): Decimal("50000"),
        date(2021, 7, 1): Decimal("70000"),  # 40% increase — would be capped when enabled
    }
    result = apply_spike_cap(earnings, enabled=False)
    assert result[date(2021, 7, 1)] == Decimal("70000")


def test_spike_cap_custom_rate():
    earnings = {
        date(2020, 7, 1): Decimal("50000"),
        date(2021, 7, 1): Decimal("57000"),  # 14% — ok under 20% cap, not under 10% cap
    }
    # 10% cap: max = 50000 * 1.10 = 55000
    result = apply_spike_cap(earnings, cap_rate=Decimal("0.10"), effective_date=date(1997, 7, 1))
    assert result[date(2021, 7, 1)] == Decimal("55000.00")


# ---------------------------------------------------------------------------
# Parameterized age reduction
# ---------------------------------------------------------------------------

def test_age_reduction_imrf_tier_i_rate():
    birth = date(1965, 1, 1)
    retirement = date(2020, 1, 1)  # age 55, 5 years short of 60
    months_short, factor = compute_age_reduction(
        "I", birth, retirement, Decimal("20"),
        tier_i_rate_per_month=Decimal("0.0025"),  # IMRF: 0.25%/month
        tier_i_normal_age=60,
        tier_i_no_reduction_years=Decimal("35"),
    )
    assert months_short == 60
    assert factor == Decimal("0.85")  # 1 - (60 * 0.0025)


def test_age_reduction_no_reduction_custom_threshold():
    birth = date(1980, 1, 1)
    retirement = date(2020, 1, 1)  # age 40
    # 35-year threshold: member has 35 years so no reduction applies
    months_short, factor = compute_age_reduction(
        "I", birth, retirement, Decimal("35"),
        tier_i_no_reduction_years=Decimal("35"),
    )
    assert months_short == 0
    assert factor == Decimal("1")


# ---------------------------------------------------------------------------
# Parameterized general formula
# ---------------------------------------------------------------------------

def test_general_formula_always_use_bands():
    # IMRF-style: always graduated, 1.667% first 15 yrs, 2.0% over 15
    bands = [
        (Decimal("15"), Decimal("0.01667")),
        (None, Decimal("0.020")),
    ]
    # 20 years: (15 × 0.01667 + 5 × 0.020) × 60000
    annual = compute_general_annual(
        Decimal("20"),
        Decimal("60000"),
        date(2024, 1, 1),  # date irrelevant when always_use_bands
        always_use_bands=True,
        bands=bands,
    )
    expected = ((Decimal("15") * Decimal("0.01667") + Decimal("5") * Decimal("0.020")) * Decimal("60000"))
    assert annual == expected.quantize(Decimal("0.01"))


def test_general_formula_custom_multiplier():
    annual = compute_general_annual(
        Decimal("25"),
        Decimal("60000"),
        date(2024, 1, 1),
        multiplier=Decimal("0.020"),
        effective_date=date(2000, 1, 1),
    )
    assert annual == Decimal("30000.00")


# ---------------------------------------------------------------------------
# Parameterized money purchase eligibility
# ---------------------------------------------------------------------------

def test_mp_eligible_no_cutoff():
    # IMRF: all members eligible
    assert is_mp_eligible(date(2020, 1, 1), cutoff_date=None) is True
    assert is_mp_eligible(date(1980, 1, 1), cutoff_date=None) is True


def test_mp_eligible_custom_cutoff():
    assert is_mp_eligible(date(2004, 6, 30), cutoff_date=date(2005, 7, 1)) is True
    assert is_mp_eligible(date(2005, 7, 1), cutoff_date=date(2005, 7, 1)) is False


# ---------------------------------------------------------------------------
# Parameterized police/fire
# ---------------------------------------------------------------------------

def test_pf_eligibility_custom_rules():
    # Rule: age 55+ with 25+ years (hypothetical stricter fund)
    rules = [(55, 25, None)]
    birth = date(1965, 1, 1)
    retirement = date(2020, 1, 1)  # age 55
    assert check_pf_eligibility(
        "I", birth, retirement, Decimal("25"), True,
        tier_i_rules=rules,
    ) is True
    assert check_pf_eligibility(
        "I", birth, retirement, Decimal("24"), True,
        tier_i_rules=rules,
    ) is False


def test_pf_max_benefit_pct_custom():
    monthly = compute_police_fire_monthly(
        Decimal("30"), Decimal("60000"),
        bands=[(Decimal("10"), Decimal("0.0225")), (Decimal("10"), Decimal("0.0250")), (None, Decimal("0.0275"))],
        max_benefit_pct=Decimal("0.70"),
    )
    # Formula gives (10×0.0225 + 10×0.0250 + 10×0.0275) = 0.75 → capped at 0.70
    cap_annual = Decimal("60000") * Decimal("0.70")
    assert monthly == (cap_annual / 12).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Parameterized max cap
# ---------------------------------------------------------------------------

def test_max_cap_custom_modern_pct():
    # IMRF Regular: 75%
    cap = determine_benefit_cap(
        date(2024, 1, 1), 65, date(2000, 1, 1),
        modern_cap_pct=Decimal("75"),
    )
    assert cap == Decimal("75")


def test_max_cap_skip_historical_table():
    # Pre-modern termination but historical table disabled
    cap = determine_benefit_cap(
        date(1990, 1, 1), 60, date(1960, 1, 1),
        modern_cap_pct=Decimal("80"),
        use_historical_table=False,
    )
    assert cap == Decimal("80")


# ---------------------------------------------------------------------------
# Parameterized COLA / AAI
# ---------------------------------------------------------------------------

def test_aai_3pct_simple_tier_i():
    rate_type, first_date, basis = compute_aai(
        "I", date(2024, 6, 15), date(1965, 1, 1), Decimal("3000"),
        tier_i_cola_type="3pct_simple",
    )
    assert rate_type == "3pct_simple"
    assert first_date == date(2025, 1, 1)


def test_aai_custom_deferral_age_tier_ii():
    birth = date(1970, 1, 1)
    # Deferral age 65, member retires at 60
    rate_type, first_date, basis = compute_aai(
        "II", date(2030, 1, 1), birth, Decimal("2000"),
        tier_ii_deferral_age=65,
    )
    assert rate_type == "cpi_u_half"
    # Age 65 date: 2035-01-01; anniversary: 2031-01-01. Later = 2035-01-01 (already Jan 1)
    assert first_date == date(2035, 1, 1)


def test_aai_fiscal_year_cola_increase():
    # Fund applies COLA on July 1 instead of January 1
    rate_type, first_date, basis = compute_aai(
        "I", date(2024, 3, 15), date(1964, 3, 15), Decimal("3000"),
        increase_month=7,
        increase_day=1,
    )
    assert rate_type == "3pct_compound"
    assert first_date == date(2024, 7, 1)  # next July 1 on/after retirement date


def test_aai_fiscal_year_cola_already_on_increase_date():
    # Retires exactly on July 1 — first increase is that same July 1
    rate_type, first_date, basis = compute_aai(
        "I", date(2024, 7, 1), date(1964, 7, 1), Decimal("3000"),
        increase_month=7,
        increase_day=1,
    )
    assert first_date == date(2024, 7, 1)


# ---------------------------------------------------------------------------
# Parameterized sick leave — proportional method
# ---------------------------------------------------------------------------

def test_sick_leave_proportional():
    # 60 days = 3 months = 0.25 years
    credit = sick_leave_credit(
        60, date(2024, 1, 1), date(2023, 12, 1),
        method="proportional",
        proportional_days_per_month=20,
        max_credit_years=Decimal("1.0"),
        min_days=20,
        max_gap_days=60,
    )
    assert credit == Decimal("0.25")


def test_sick_leave_proportional_capped():
    credit = sick_leave_credit(
        300, date(2024, 1, 1), date(2023, 12, 1),
        method="proportional",
        proportional_days_per_month=20,
        max_credit_years=Decimal("1.0"),
        min_days=20,
        max_gap_days=60,
    )
    assert credit == Decimal("1.0")


def test_sick_leave_custom_gap_limit():
    # Gap of 45 days, but max_gap_days set to 30
    credit = sick_leave_credit(
        180, date(2024, 1, 1), date(2023, 11, 17),  # 45 days gap
        max_gap_days=30,
    )
    assert credit == Decimal("0")

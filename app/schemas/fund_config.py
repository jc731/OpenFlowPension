"""Fund-specific calculation configuration.

All fields default to SURS values. A fund overrides only what differs.
Stored in system_configurations under key 'fund_calculation_config' as JSONB.
If that key is absent, FundConfig() is used (SURS rules apply).

IMRF comparison notes are inline so it is clear what each parameter controls.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class FormulaBand(BaseModel):
    """One tier in a graduated benefit formula."""
    years: Decimal | None = None  # None means "all remaining service"
    rate: Decimal


class SickLeaveStep(BaseModel):
    """One row in a step-table sick leave conversion schedule."""
    min_days: int
    credit_years: Decimal


class PfEligibilityRule(BaseModel):
    """One age+service combination that grants P/F eligibility (Tier I)."""
    min_age: int
    min_pf_years: int
    max_pf_years: int | None = None  # None = no upper bound


class FundConfig(BaseModel):
    """Calculation parameters for a single pension fund.

    All defaults produce SURS-identical results. Override any field to adapt
    the engine for another fund (e.g., IMRF).
    """
    model_config = ConfigDict(from_attributes=False)

    # ── Tier determination ────────────────────────────────────────────────────
    # SURS: 2011-01-01.  IMRF: 2011-01-01 (same).
    tier_cutoff_date: date = date(2011, 1, 1)

    # ── FAE window ────────────────────────────────────────────────────────────
    # SURS: 4 consecutive AYs (Tier I); 8 in last 10 AYs (Tier II).
    # IMRF: 48 months (Tier I); 96 months in last 10 yrs (Tier II) — same years.
    fae_tier_i_years: int = 4
    fae_tier_ii_years: int = 8
    fae_tier_ii_restrict_last_n_years: int | None = 10  # None = no restriction

    # Academic year convention: Jul 1 – Jun 30 for SURS; not used by IMRF.
    fae_academic_year_start_month: int = 7
    fae_academic_year_start_day: int = 1

    # SURS: 20% YoY spike cap after 1997-07-01.
    # IMRF: no spike cap (Tier II has an absolute wage cap instead).
    fae_spike_cap_enabled: bool = True
    fae_spike_cap_rate: Decimal = Decimal("0.20")
    fae_spike_cap_effective_date: date = date(1997, 7, 1)

    # ── General Formula ───────────────────────────────────────────────────────
    # SURS: 2.2% flat rate for service on/after 1997-07-07; graduated before.
    # IMRF: 1.667% for first 15 yrs, 2.0% over 15 yrs — no date break.
    general_formula_multiplier: Decimal = Decimal("0.022")       # SURS modern flat rate
    general_formula_effective_date: date = date(1997, 7, 7)     # before: use pre_bands

    # Pre-modern graduated bands (SURS only; other funds ignore if always_use_bands=True)
    general_formula_pre_bands: list[FormulaBand] = [
        FormulaBand(years=Decimal("10"), rate=Decimal("0.0167")),
        FormulaBand(years=Decimal("10"), rate=Decimal("0.0190")),
        FormulaBand(years=Decimal("10"), rate=Decimal("0.0210")),
        FormulaBand(years=None,          rate=Decimal("0.0230")),
    ]

    # Set True for funds whose formula is always graduated (e.g., IMRF).
    # When True, general_formula_bands is used for all service; effective_date ignored.
    general_formula_always_use_bands: bool = False
    general_formula_bands: list[FormulaBand] = []  # populated for IMRF-style funds

    # ── Age Reduction ─────────────────────────────────────────────────────────
    # SURS: 0.5%/month both tiers, no reduction at 30+ yrs (Tier I).
    # IMRF: 0.25%/month Tier I, 0.5%/month Tier II; no reduction at 35+ yrs.
    age_reduction_tier_i_normal_age: int = 60
    age_reduction_tier_i_rate_per_month: Decimal = Decimal("0.005")
    age_reduction_tier_i_no_reduction_years: Decimal = Decimal("30")
    age_reduction_tier_ii_normal_age: int = 67
    age_reduction_tier_ii_rate_per_month: Decimal = Decimal("0.005")

    # ── Max Benefit Cap ───────────────────────────────────────────────────────
    # SURS: 80%.  IMRF Regular: 75%.  IMRF SLEP Tier I: 80%.
    max_benefit_cap_pct: Decimal = Decimal("80")
    max_benefit_cap_modern_date: date = date(1997, 7, 7)
    # When False, historical pre-modern cap table is skipped and modern % is used for all.
    max_benefit_cap_use_historical_table: bool = True

    # ── COLA / AAI ────────────────────────────────────────────────────────────
    # SURS Tier I: 3% compound.  IMRF Tier I: 3% simple (of original benefit).
    cola_tier_i_type: Literal["3pct_compound", "3pct_simple"] = "3pct_compound"
    # SURS Tier II: half CPI.  IMRF Tier II: half CPI.  Deferral age differs (both 67).
    cola_tier_ii_type: Literal["half_cpi"] = "half_cpi"
    cola_tier_ii_deferral_age: int = 67

    # ── Sick Leave Conversion ─────────────────────────────────────────────────
    # SURS: step_table (20/60/120/180 days → 0.25/0.5/0.75/1.0 yrs), 60-day gap.
    # IMRF: proportional (1 month per 20 days, max 240 days = 1.0 yr), no gap limit.
    sick_leave_method: Literal["step_table", "proportional"] = "step_table"
    sick_leave_step_table: list[SickLeaveStep] = [
        SickLeaveStep(min_days=180, credit_years=Decimal("1.00")),
        SickLeaveStep(min_days=120, credit_years=Decimal("0.75")),
        SickLeaveStep(min_days=60,  credit_years=Decimal("0.50")),
        SickLeaveStep(min_days=20,  credit_years=Decimal("0.25")),
    ]
    sick_leave_proportional_days_per_month: int = 20
    sick_leave_max_credit_years: Decimal = Decimal("1.0")
    sick_leave_min_days: int = 20
    sick_leave_max_gap_days: int = 60  # days between termination and retirement

    # ── HB2616 Minimum Floor ──────────────────────────────────────────────────
    # SURS-specific. Set enabled=False for other funds.
    hb2616_enabled: bool = True
    hb2616_per_service_year: Decimal = Decimal("25")
    hb2616_max_service_years: Decimal = Decimal("30")

    # ── Money Purchase ────────────────────────────────────────────────────────
    # SURS: eligible if cert_date < 2005-07-01.  IMRF: all members eligible (None).
    mp_eligibility_cutoff_date: date | None = date(2005, 7, 1)

    # ── Police / Fire ─────────────────────────────────────────────────────────
    # SURS: 9.5% contribution rate required.  IMRF SLEP: 7.5%.
    pf_contribution_rate_threshold: Decimal = Decimal("0.095")
    pf_formula_bands: list[FormulaBand] = [
        FormulaBand(years=Decimal("10"), rate=Decimal("0.0225")),
        FormulaBand(years=Decimal("10"), rate=Decimal("0.0250")),
        FormulaBand(years=None,          rate=Decimal("0.0275")),
    ]
    pf_max_benefit_pct: Decimal = Decimal("0.80")
    # Tier I eligibility rules (any matching rule grants eligibility)
    pf_tier_i_eligibility: list[PfEligibilityRule] = [
        PfEligibilityRule(min_age=50, min_pf_years=25),
        PfEligibilityRule(min_age=55, min_pf_years=20, max_pf_years=25),
    ]
    pf_tier_ii_min_age: int = 60
    pf_tier_ii_min_years: int = 20

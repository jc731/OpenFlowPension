"""Age reduction factor computation.

Tier I: 0.5%/month short of age 60. No reduction if service >= 30 years.
Tier II: 0.5%/month short of age 67.
"""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from app.services.benefit.eligibility import age_in_months

_DEFAULT_TIER_I_AGE = 60
_DEFAULT_TIER_II_AGE = 67
_DEFAULT_RATE = Decimal("0.005")
_DEFAULT_NO_REDUCTION_YEARS = Decimal("30")


def compute_age_reduction(
    tier: str,
    birth_date: date,
    retirement_date: date,
    total_service_years: Decimal,
    *,
    tier_i_normal_age: int = _DEFAULT_TIER_I_AGE,
    tier_i_rate_per_month: Decimal = _DEFAULT_RATE,
    tier_i_no_reduction_years: Decimal = _DEFAULT_NO_REDUCTION_YEARS,
    tier_ii_normal_age: int = _DEFAULT_TIER_II_AGE,
    tier_ii_rate_per_month: Decimal = _DEFAULT_RATE,
) -> tuple[int, Decimal]:
    """Return (months_short, reduction_factor). Factor is 1.0 if no reduction applies."""
    age_months = age_in_months(birth_date, retirement_date)

    if tier == "I":
        if total_service_years >= tier_i_no_reduction_years:
            return 0, Decimal("1")
        months_short = max(0, tier_i_normal_age * 12 - age_months)
        rate = tier_i_rate_per_month
    elif tier == "II":
        months_short = max(0, tier_ii_normal_age * 12 - age_months)
        rate = tier_ii_rate_per_month
    else:
        months_short = 0
        rate = _DEFAULT_RATE

    if months_short == 0:
        return 0, Decimal("1")

    factor = (Decimal("1") - Decimal(str(months_short)) * rate).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )
    factor = max(Decimal("0"), factor)
    return months_short, factor

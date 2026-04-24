"""Age reduction factor computation.

Tier I: 0.5%/month short of age 60. No reduction if service >= 30 years.
Tier II: 0.5%/month short of age 67.
"""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from app.services.benefit.eligibility import age_in_months

TIER_I_NORMAL_AGE_MONTHS = 60 * 12
TIER_II_NORMAL_AGE_MONTHS = 67 * 12
REDUCTION_PER_MONTH = Decimal("0.005")


def compute_age_reduction(
    tier: str,
    birth_date: date,
    retirement_date: date,
    total_service_years: Decimal,
) -> tuple[int, Decimal]:
    """Return (months_short, reduction_factor). Factor is 1.0 if no reduction applies."""
    age_months = age_in_months(birth_date, retirement_date)

    if tier == "I":
        if total_service_years >= Decimal("30"):
            return 0, Decimal("1")
        months_short = max(0, TIER_I_NORMAL_AGE_MONTHS - age_months)
    elif tier == "II":
        months_short = max(0, TIER_II_NORMAL_AGE_MONTHS - age_months)
    else:
        months_short = 0

    if months_short == 0:
        return 0, Decimal("1")

    factor = (Decimal("1") - Decimal(str(months_short)) * REDUCTION_PER_MONTH).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )
    factor = max(Decimal("0"), factor)
    return months_short, factor

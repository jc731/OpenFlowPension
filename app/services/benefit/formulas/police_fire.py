"""Police/Firefighter Formula (graduated, capped at 80%).

Tier I eligibility:
  - Contributed 9.5% AND (age 50+ with 25+ years P/F) OR (age 55+ with 20-24 years P/F)

Tier II eligibility:
  - Age 60+ with 20+ years P/F (no age reduction)

Formula (applied to police_fire FAE):
  First 10 yrs × 2.25%
  Second 10 yrs × 2.50%
  Third 10+ yrs × 2.75%
  Sum capped at 80%
"""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from app.services.benefit.eligibility import age_years_months

_TIERS = [
    (Decimal("10"), Decimal("0.0225")),
    (Decimal("10"), Decimal("0.0250")),
    (None, Decimal("0.0275")),
]


def check_pf_eligibility(
    tier: str,
    birth_date: date,
    retirement_date: date,
    pf_service_years: Decimal,
    contributed_9_5_pct: bool,
) -> bool:
    age_y, _ = age_years_months(birth_date, retirement_date)
    pf = float(pf_service_years)

    if tier == "I":
        if not contributed_9_5_pct:
            return False
        return (age_y >= 50 and pf >= 25) or (age_y >= 55 and 20 <= pf < 25)

    if tier == "II":
        return age_y >= 60 and pf >= 20

    return False


def compute_police_fire_monthly(
    pf_service_years: Decimal,
    pf_fae_annual: Decimal,
) -> Decimal:
    remaining = pf_service_years
    pct_sum = Decimal("0")
    for band_years, rate in _TIERS:
        if band_years is None:
            years_in_band = remaining
        else:
            years_in_band = min(remaining, band_years)
        pct_sum += years_in_band * rate
        remaining -= years_in_band
        if remaining <= 0:
            break

    pct_sum = min(pct_sum, Decimal("0.80"))
    annual = (pct_sum * pf_fae_annual).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return (annual / 12).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

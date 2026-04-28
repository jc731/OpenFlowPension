"""Police/Firefighter Formula (graduated, capped at 80%).

Tier I eligibility:
  - Contributed at threshold rate AND matches one of the configured eligibility rules.

Tier II eligibility:
  - Age >= tier_ii_min_age with >= tier_ii_min_years P/F service.

Formula (applied to police_fire FAE) uses configurable graduated bands, capped at
max_benefit_pct.
"""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from app.services.benefit.eligibility import age_years_months

# SURS defaults
_DEFAULT_BANDS: list[tuple[Decimal | None, Decimal]] = [
    (Decimal("10"), Decimal("0.0225")),
    (Decimal("10"), Decimal("0.0250")),
    (None, Decimal("0.0275")),
]
# Each rule: (min_age, min_pf_years, max_pf_years | None)
_DEFAULT_TIER_I_RULES: list[tuple[int, int, int | None]] = [
    (50, 25, None),
    (55, 20, 25),
]
_DEFAULT_TIER_II_MIN_AGE = 60
_DEFAULT_TIER_II_MIN_YEARS = 20
_DEFAULT_MAX_PCT = Decimal("0.80")


def check_pf_eligibility(
    tier: str,
    birth_date: date,
    retirement_date: date,
    pf_service_years: Decimal,
    contributed_threshold: bool,
    *,
    tier_i_rules: list[tuple[int, int, int | None]] = _DEFAULT_TIER_I_RULES,
    tier_ii_min_age: int = _DEFAULT_TIER_II_MIN_AGE,
    tier_ii_min_years: int = _DEFAULT_TIER_II_MIN_YEARS,
) -> bool:
    age_y, _ = age_years_months(birth_date, retirement_date)
    pf = float(pf_service_years)

    if tier == "I":
        if not contributed_threshold:
            return False
        for min_age, min_yrs, max_yrs in tier_i_rules:
            if age_y >= min_age and pf >= min_yrs:
                if max_yrs is None or pf < max_yrs:
                    return True
        return False

    if tier == "II":
        return age_y >= tier_ii_min_age and pf >= tier_ii_min_years

    return False


def compute_police_fire_monthly(
    pf_service_years: Decimal,
    pf_fae_annual: Decimal,
    *,
    bands: list[tuple[Decimal | None, Decimal]] = _DEFAULT_BANDS,
    max_benefit_pct: Decimal = _DEFAULT_MAX_PCT,
) -> Decimal:
    remaining = pf_service_years
    pct_sum = Decimal("0")
    for band_years, rate in bands:
        if band_years is None:
            years_in_band = remaining
        else:
            years_in_band = min(remaining, band_years)
        pct_sum += years_in_band * rate
        remaining -= years_in_band
        if remaining <= 0:
            break

    pct_sum = min(pct_sum, max_benefit_pct)
    annual = (pct_sum * pf_fae_annual).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return (annual / 12).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

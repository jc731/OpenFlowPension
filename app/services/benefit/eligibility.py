from datetime import date
from decimal import Decimal

TIER_I_CUTOFF = date(2011, 1, 1)
ANY_AGE_30_YRS_MIN_TERM_DATE = date(2002, 8, 2)


def determine_tier(cert_date: date) -> str:
    return "I" if cert_date < TIER_I_CUTOFF else "II"


def age_years_months(birth_date: date, as_of: date) -> tuple[int, int]:
    """Returns (whole_years, remaining_months) of age as of a date."""
    years = as_of.year - birth_date.year
    months = as_of.month - birth_date.month
    if as_of.day < birth_date.day:
        months -= 1
    if months < 0:
        years -= 1
        months += 12
    return years, months


def age_in_months(birth_date: date, as_of: date) -> int:
    years, months = age_years_months(birth_date, as_of)
    return years * 12 + months


def check_eligibility(
    tier: str,
    birth_date: date,
    retirement_date: date,
    termination_date: date,
    service_years: Decimal,
) -> tuple[bool, str]:
    """Returns (eligible, reason). reason is empty string when eligible."""
    age_y, _ = age_years_months(birth_date, retirement_date)
    svc = float(service_years)

    if tier == "I":
        if svc >= 30 and termination_date >= ANY_AGE_30_YRS_MIN_TERM_DATE:
            return True, ""
        if age_y >= 62 and svc >= 5:
            return True, ""
        if age_y >= 55 and svc >= 8:
            return True, ""
        return False, (
            "Tier I requires: age 62+ with 5+ years, age 55+ with 8+ years, "
            "or 30+ years service (term on/after 2002-08-02)"
        )

    if tier == "II":
        if age_y >= 62 and svc >= 10:
            return True, ""
        return False, "Tier II requires: age 62+ with 10+ years service"

    return False, f"Unknown tier: {tier}"
